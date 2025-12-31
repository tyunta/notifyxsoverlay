from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .app import APP_NAME

DEFAULT_WS_URL = f"ws://127.0.0.1:42070/?client={APP_NAME}"


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
            "shown_today": {},
        },
        "xs_overlay": {
            "ws_url": DEFAULT_WS_URL,
        },
        "poll_interval_seconds": 1.0,
    }


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
    if not isinstance(learning.get("shown_today"), dict):
        learning["shown_today"] = {}
    merged["filters"] = filters
    merged["learning"] = learning
    return merged


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_config()
    if not isinstance(data, dict):
        return default_config()
    return normalize_config(data)


def save_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(serialized, encoding="utf-8")


def reset_learning_state(config: dict[str, Any]) -> bool:
    today = date.today().isoformat()
    learning = config.get("learning", {})
    last_reset = learning.get("last_reset")
    if last_reset != today:
        learning["last_reset"] = today
        learning["pending"] = {}
        learning["shown_today"] = {}
        return True
    return False
