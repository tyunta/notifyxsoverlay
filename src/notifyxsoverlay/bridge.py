from __future__ import annotations

import asyncio
import json
import time
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


async def _request_access(listener: Any) -> Any:
    method = getattr(listener, "request_access_async", None) or getattr(listener, "RequestAccessAsync", None)
    if method is None:
        raise RuntimeError("RequestAccessAsync not available")
    return await method()


async def _get_notifications(listener: Any, kind: Any) -> list[Any]:
    method = getattr(listener, "get_notifications_async", None) or getattr(listener, "GetNotificationsAsync", None)
    if method is None:
        raise RuntimeError("GetNotificationsAsync not available")
    return await method(kind)


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


def _build_notification_payload(title: str, content: str) -> dict[str, Any]:
    return {
        "title": title,
        "content": content,
        "sourceApp": APP_NAME,
        "type": 1,
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
    websocket: Any | None,
) -> tuple[bool, Any | None, str | None]:
    try:
        import websockets  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"websockets import failed: {exc}") from exc

    normalized_url = _ensure_client_param(ws_url)
    notification = _build_notification_payload(title, content)
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


def _evaluate_notification(
    app_key: str,
    display_name: str,
    config: dict[str, Any],
) -> tuple[bool, str, bool]:
    filters = config.get("filters", {})
    allow_list = set(filters.get("allow", []))
    block_list = set(filters.get("block", []))

    if app_key in block_list:
        return False, "blocked", False
    if app_key in allow_list:
        return True, "allowed", False

    learning = config.get("learning", {})
    if learning.get("enabled", True):
        pending = learning.setdefault("pending", {})
        changed = False
        if app_key not in pending:
            pending[app_key] = display_name or app_key
            changed = True
        shown_today = learning.setdefault("shown_today", {})
        if app_key not in shown_today:
            shown_today[app_key] = datetime.now().date().isoformat()
            return True, "learning_allow", True
        return False, "learning_suppress", changed

    if allow_list:
        return False, "not_in_allow", False
    return True, "default_allow", False


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
    try:
        if value is None:
            return 1.0
        interval = float(value)
        return interval if interval > 0 else 1.0
    except Exception:
        return 1.0


async def run_bridge(ws_url: str | None, poll_interval: float | None) -> int:
    config_path = get_config_path()
    config = load_config(config_path)
    if ws_url:
        config.setdefault("xs_overlay", {})["ws_url"] = ws_url
    if poll_interval is not None:
        config["poll_interval_seconds"] = poll_interval

    dirty = reset_learning_state(config)
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

    log_event("info", "run_start", ws_url=ws_url_value)

    seen: dict[str, float] = {}
    last_config_mtime = config_path.stat().st_mtime if config_path.exists() else 0.0
    websocket: Any | None = None
    current_ws_url = ws_url_value
    last_send_error_at = 0.0
    send_error_interval = 30.0

    while True:
        if config_path.exists():
            mtime = config_path.stat().st_mtime
            if mtime > last_config_mtime:
                config = load_config(config_path)
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
        if reset_learning_state(config):
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

            allow, reason, updated = _evaluate_notification(app_key, display_name, config)
            if updated:
                changed = True
            if not allow:
                log_event("info", "notification_suppressed", app=app_key, reason=reason)
                continue

            try:
                ok, websocket, send_error = await _send_xs_notification(
                    ws_url_value,
                    title=title,
                    content=content,
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
