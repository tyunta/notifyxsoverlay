# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ちゅんた

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .app import APP_NAME, get_config_path
from .config import load_config, reset_learning_state, save_config
from .log import log_event


def _get_attr(obj: Any, *names: str) -> Any | None:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _call(obj: Any, *names: str) -> Any | None:
    for name in names:
        func = getattr(obj, name, None)
        if callable(func):
            return func()
    return None


def _get_toast_kind(notification_kinds: Any) -> Any:
    for name in ("TOAST", "Toast"):
        if hasattr(notification_kinds, name):
            return getattr(notification_kinds, name)
    return notification_kinds


async def _call_async_method(obj: Any, names: tuple[str, ...], error_message: str, *args: Any) -> Any:
    method = None
    for name in names:
        candidate = getattr(obj, name, None)
        if callable(candidate):
            method = candidate
            break
    if method is None:
        raise RuntimeError(error_message)
    return await method(*args)


async def _request_access(listener: Any) -> Any:
    return await _call_async_method(
        listener,
        ("request_access_async", "RequestAccessAsync"),
        "RequestAccessAsync not available",
    )


async def _get_notifications(listener: Any, kind: Any) -> list[Any]:
    return await _call_async_method(
        listener,
        ("get_notifications_async", "GetNotificationsAsync"),
        "GetNotificationsAsync not available",
        kind,
    )


def _access_allowed(status: Any, status_enum: Any) -> bool:
    allowed = getattr(status_enum, "ALLOWED", None) or getattr(status_enum, "Allowed", None)
    return status == allowed


def _extract_app_info(user_notification: Any) -> tuple[str, str]:
    app_info = _get_attr(user_notification, "app_info", "AppInfo")
    app_id = None
    display_name = None
    if app_info is not None:
        app_id = _get_attr(app_info, "app_user_model_id", "AppUserModelId")
        display_info = _get_attr(app_info, "display_info", "DisplayInfo")
        if display_info is not None:
            display_name = _get_attr(display_info, "display_name", "DisplayName")
    app_id = app_id or ""
    display_name = display_name or ""
    return app_id, display_name


def _extract_text_elements(user_notification: Any) -> list[str]:
    notification = _get_attr(user_notification, "notification", "Notification")
    if notification is None:
        return []
    visual = _get_attr(notification, "visual", "Visual")
    if visual is None:
        return []
    bindings = _get_attr(visual, "bindings", "Bindings")
    if bindings is None:
        return []
    texts: list[str] = []
    for binding in bindings:
        elements = _call(binding, "get_text_elements", "GetTextElements")
        if not elements:
            continue
        for element in elements:
            text = _get_attr(element, "text", "Text")
            if text:
                texts.append(text)
    return texts


def _notification_key(user_notification: Any, app_key: str) -> str:
    notif_id = _get_attr(user_notification, "id", "Id")
    if notif_id is None:
        created = _get_attr(user_notification, "creation_time", "CreationTime")
        if isinstance(created, datetime):
            return f"{app_key}:{created.isoformat()}"
        return f"{app_key}:{id(user_notification)}"
    return f"{app_key}:{notif_id}"


def _prune_seen(seen: dict[str, float], max_age_seconds: float = 86400.0, max_size: int = 2000) -> None:
    now = time.time()
    for key, ts in list(seen.items()):
        if now - ts > max_age_seconds:
            del seen[key]
    if len(seen) > max_size:
        for key, _ in sorted(seen.items(), key=lambda item: item[1])[: len(seen) - max_size]:
            del seen[key]


def _ensure_client_param(ws_url: str) -> str:
    if "?client=" in ws_url or "&client=" in ws_url:
        return ws_url
    joiner = "&" if "?" in ws_url else "?"
    return f"{ws_url}{joiner}client={APP_NAME}"


def _build_notification_payload(
    title: str,
    content: str,
    timeout_seconds: float,
    opacity: float,
) -> dict[str, Any]:
    return {
        "title": title,
        "content": content,
        "sourceApp": APP_NAME,
        "type": 1,
        "timeout": timeout_seconds,
        "opacity": opacity,
    }


def _build_ws_message(notification: dict[str, Any]) -> dict[str, Any]:
    return {
        "sender": APP_NAME,
        "target": "xsoverlay",
        "command": "SendNotification",
        "jsonData": json.dumps(notification, ensure_ascii=False),
    }


async def _send_xs_notification(
    ws_url: str,
    title: str,
    content: str,
    timeout_seconds: float,
    opacity: float,
    websocket: Any | None,
) -> tuple[bool, Any | None, str | None]:
    try:
        import websockets  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"websockets import failed: {exc}") from exc

    normalized_url = _ensure_client_param(ws_url)
    notification = _build_notification_payload(title, content, timeout_seconds, opacity)
    message = _build_ws_message(notification)

    if websocket is None or getattr(websocket, "closed", False):
        websocket = await websockets.connect(normalized_url)

    try:
        await websocket.send(json.dumps(message, ensure_ascii=False))
        return True, websocket, None
    except Exception as exc:
        try:
            await websocket.close()
        except Exception:
            pass
        return False, None, str(exc)


@dataclass(frozen=True)
class FilterDecision:
    allow: bool
    reason: str
    updated: bool = False


class NotificationFilter:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        filters = config.get("filters", {})
        self._allow_list = set(filters.get("allow", []))
        self._block_list = set(filters.get("block", []))
        self._learning = config.get("learning", {})

    def evaluate(self, app_key: str, display_name: str) -> FilterDecision:
        if app_key in self._block_list:
            return FilterDecision(False, "blocked", False)
        if app_key in self._allow_list:
            return FilterDecision(True, "allowed", False)

        if self._learning.get("enabled", True):
            pending = self._learning.setdefault("pending", {})
            changed = False
            if app_key not in pending:
                pending[app_key] = display_name or app_key
                changed = True
            shown_session = self._learning.setdefault("shown_session", {})
            if app_key not in shown_session:
                shown_session[app_key] = datetime.now().isoformat()
                return FilterDecision(True, "learning_allow", True)
            return FilterDecision(False, "learning_suppress", changed)

        if self._allow_list:
            return FilterDecision(False, "not_in_allow", False)
        return FilterDecision(True, "default_allow", False)


def _evaluate_notification(
    app_key: str,
    display_name: str,
    config: dict[str, Any],
) -> FilterDecision:
    return NotificationFilter(config).evaluate(app_key, display_name)


async def _init_listener() -> tuple[Any, Any, Any] | None:
    try:
        from winrt.windows.foundation.metadata import ApiInformation  # type: ignore
        from winrt.windows.ui.notifications import NotificationKinds  # type: ignore
        from winrt.windows.ui.notifications.management import (  # type: ignore
            UserNotificationListener,
            UserNotificationListenerAccessStatus,
        )
    except Exception as exc:
        log_event("error", "winrt_import_failed", error=str(exc))
        return None

    if not ApiInformation.is_type_present(
        "Windows.UI.Notifications.Management.UserNotificationListener"
    ):
        log_event("error", "notification_listener_unavailable")
        return None

    listener = _get_attr(UserNotificationListener, "current", "Current")
    if callable(listener):
        listener = listener()
    if listener is None:
        listener = _call(UserNotificationListener, "get_current", "GetCurrent")

    if listener is None:
        log_event("error", "notification_listener_missing")
        return None

    access = await _request_access(listener)
    if not _access_allowed(access, UserNotificationListenerAccessStatus):
        log_event(
            "error",
            "notification_access_denied",
            status=str(access),
            hint="Enable notification access in Windows settings and retry.",
        )
        return None

    return listener, NotificationKinds, UserNotificationListenerAccessStatus


def _build_display(title: str, texts: list[str], display_name: str, app_key: str) -> tuple[str, str]:
    if display_name:
        title = display_name
        content = "\n".join(texts)
        return title, content
    if not title:
        title = app_key
    content = "\n".join(texts[1:]) if len(texts) > 1 else ""
    return title, content


def _safe_poll_interval(value: Any) -> float:
    return _safe_float(value, default=1.0, min_value=0.0, allow_zero=False)


def _safe_notification_timeout(value: Any) -> float:
    return _safe_float(value, default=3.0, min_value=0.0, allow_zero=False)


def _safe_notification_opacity(value: Any) -> float:
    return _safe_float(value, default=0.6, min_value=0.0, max_value=1.0, allow_zero=True)


def _safe_float(
    value: Any,
    default: float,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    allow_zero: bool = True,
) -> float:
    try:
        if value is None:
            return default
        number = float(value)
    except Exception:
        return default
    if min_value is not None:
        if allow_zero:
            if number < min_value:
                return default
        else:
            if number <= min_value:
                return default
    if max_value is not None and number > max_value:
        return default
    return number


async def run_bridge(ws_url: str | None, poll_interval: float | None) -> int:
    config_path = get_config_path()
    config = load_config(config_path)
    if ws_url:
        config.setdefault("xs_overlay", {})["ws_url"] = ws_url
    if poll_interval is not None:
        config["poll_interval_seconds"] = poll_interval

    session_id = datetime.now().isoformat()
    dirty = reset_learning_state(config, session_id)
    if dirty:
        save_config(config_path, config)

    listener_info = await _init_listener()
    if listener_info is None:
        return 1
    listener, notification_kinds, _ = listener_info
    toast_kind = _get_toast_kind(notification_kinds)

    ws_url_value = config.get("xs_overlay", {}).get("ws_url", "")
    if not ws_url_value:
        log_event("error", "ws_url_missing")
        return 1

    poll_delay = _safe_poll_interval(config.get("poll_interval_seconds"))
    notification_timeout = _safe_notification_timeout(
        config.get("xs_overlay", {}).get("notification_timeout_seconds")
    )
    notification_opacity = _safe_notification_opacity(
        config.get("xs_overlay", {}).get("notification_opacity")
    )

    log_event("info", "run_start", ws_url=ws_url_value)

    seen: dict[str, float] = {}
    if config_path.exists():
        try:
            last_config_mtime = config_path.stat().st_mtime
        except FileNotFoundError:
            last_config_mtime = 0.0
    else:
        last_config_mtime = 0.0
    websocket: Any | None = None
    current_ws_url = ws_url_value
    last_send_error_at = 0.0
    send_error_interval = 30.0

    while True:
        if config_path.exists():
            try:
                mtime = config_path.stat().st_mtime
            except FileNotFoundError:
                mtime = None
            if mtime is not None and mtime > last_config_mtime:
                config = load_config(config_path, fallback=config)
                last_config_mtime = mtime
                ws_url_value = config.get("xs_overlay", {}).get("ws_url", "")
                if not ws_url_value:
                    log_event("error", "ws_url_missing")
                    return 1
                if ws_url_value != current_ws_url:
                    current_ws_url = ws_url_value
                    if websocket is not None:
                        try:
                            await websocket.close()
                        except Exception:
                            pass
                        websocket = None
                poll_delay = _safe_poll_interval(config.get("poll_interval_seconds"))
                notification_timeout = _safe_notification_timeout(
                    config.get("xs_overlay", {}).get("notification_timeout_seconds")
                )
                notification_opacity = _safe_notification_opacity(
                    config.get("xs_overlay", {}).get("notification_opacity")
                )
        if reset_learning_state(config, session_id):
            save_config(config_path, config)

        try:
            notifications = await _get_notifications(listener, toast_kind)
        except Exception as exc:
            log_event("error", "notification_poll_failed", error=str(exc))
            await asyncio.sleep(max(poll_delay, 1.0))
            continue

        changed = False
        for user_notification in notifications:
            app_id, display_name = _extract_app_info(user_notification)
            app_key = app_id or display_name or "unknown"
            key = _notification_key(user_notification, app_key)
            if key in seen:
                continue
            seen[key] = time.time()

            texts = _extract_text_elements(user_notification)
            title = texts[0] if texts else ""
            title, content = _build_display(title, texts, display_name, app_key)

            decision = _evaluate_notification(app_key, display_name, config)
            if decision.updated:
                changed = True
            if not decision.allow:
                log_event("info", "notification_suppressed", app=app_key, reason=decision.reason)
                continue

            try:
                ok, websocket, send_error = await _send_xs_notification(
                    ws_url_value,
                    title=title,
                    content=content,
                    timeout_seconds=notification_timeout,
                    opacity=notification_opacity,
                    websocket=websocket,
                )
                if ok:
                    log_event("info", "notification_sent", app=app_key)
                else:
                    now = time.time()
                    if now - last_send_error_at >= send_error_interval:
                        log_event(
                            "error",
                            "notification_send_failed",
                            error=send_error or "send_failed",
                            app=app_key,
                        )
                        last_send_error_at = now
            except Exception as exc:
                now = time.time()
                if now - last_send_error_at >= send_error_interval:
                    log_event("error", "notification_send_failed", error=str(exc), app=app_key)
                    last_send_error_at = now

        if changed:
            save_config(config_path, config)
        _prune_seen(seen)
        await asyncio.sleep(poll_delay)
