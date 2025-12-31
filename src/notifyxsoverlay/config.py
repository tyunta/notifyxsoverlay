from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .app import APP_NAME
from .log import log_event

DEFAULT_WS_URL = f"ws://127.0.0.1:42070/?client={APP_NAME}"
BACKUP_SUFFIX = ".bak"
TEMP_SUFFIX = ".tmp"


def default_config() -> dict[str, Any]:
    return {
        "filters": {
            "allow": ["com.squirrel.Discord.Discord"],
            "block": [],
        },
        "learning": {
            "enabled": True,
            "last_reset": None,
            "pending": {},
            "shown_session": {},
        },
        "xs_overlay": {
            "ws_url": DEFAULT_WS_URL,
            "notification_timeout_seconds": 3.0,
            "notification_opacity": 0.6,
        },
        "poll_interval_seconds": 1.0,
    }


def _backup_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + BACKUP_SUFFIX)


def _temp_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + TEMP_SUFFIX)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _deep_merge(defaults: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in defaults.items():
        if key in data:
            if isinstance(value, dict) and isinstance(data[key], dict):
                merged[key] = _deep_merge(value, data[key])
            else:
                merged[key] = data[key]
        else:
            merged[key] = value
    for key, value in data.items():
        if key not in merged:
            merged[key] = value
    return merged


def normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_merge(default_config(), data)
    filters = merged.get("filters", {})
    if not isinstance(filters.get("allow"), list):
        filters["allow"] = []
    if not isinstance(filters.get("block"), list):
        filters["block"] = []
    learning = merged.get("learning", {})
    if not isinstance(learning.get("pending"), dict):
        learning["pending"] = {}
    shown_session = learning.get("shown_session")
    if not isinstance(shown_session, dict):
        shown_legacy = learning.get("shown_today")
        if isinstance(shown_legacy, dict):
            learning["shown_session"] = shown_legacy
        else:
            learning["shown_session"] = {}
    if "shown_today" in learning:
        learning.pop("shown_today", None)
    merged["filters"] = filters
    merged["learning"] = learning
    return merged


def load_config(path: Path, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default_config()
    data = _read_json(path)
    if data is not None:
        return normalize_config(data)
    backup_path = _backup_path(path)
    backup_data = _read_json(backup_path) if backup_path.exists() else None
    if backup_data is not None:
        normalized = normalize_config(backup_data)
        try:
            serialized = json.dumps(normalized, indent=2, ensure_ascii=False)
            _write_text_atomic(path, serialized, backup=False)
            log_event(
                "warning",
                "config_restore",
                restored_from=str(backup_path),
                restored_to=str(path),
            )
        except Exception as exc:
            log_event("error", "config_restore_failed", error=str(exc))
        return normalized
    log_event("warning", "config_invalid", path=str(path))
    if fallback is not None:
        return fallback
    return default_config()


def _write_text_atomic(path: Path, content: str, backup: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _temp_path(path)
    tmp_path.write_text(content, encoding="utf-8")
    if backup and path.exists():
        try:
            shutil.copyfile(path, _backup_path(path))
        except Exception as exc:
            log_event("warning", "config_backup_failed", error=str(exc))
    tmp_path.replace(path)


def save_config(path: Path, data: dict[str, Any]) -> None:
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    try:
        _write_text_atomic(path, serialized, backup=True)
    except Exception as exc:
        log_event("warning", "config_save_failed", error=str(exc), path=str(path))


def reset_learning_state(config: dict[str, Any], session_id: str) -> bool:
    learning = config.get("learning", {})
    last_reset = learning.get("last_reset")
    if last_reset != session_id:
        learning["last_reset"] = session_id
        learning["shown_session"] = {}
        return True
    return False
