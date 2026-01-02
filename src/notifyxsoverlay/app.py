# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ちゅんた

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .log import log_event
APP_KEY = "com.tyunta.notifyxsoverlay"
APP_NAME = "NotifyXSOverlay"
APP_DIR_NAME = "NotifyXSOverlay"
APP_COMMAND = "notifyxsoverlay"
WRAPPER_NAME = "notifyxsoverlay.cmd"
MANIFEST_NAME = "notifyxsoverlay.vrmanifest"
DEFAULT_REPO = "git+https://github.com/tyunta/notifyxsoverlay"
CONFIG_FILE_NAME = "config.json"
_SINGLE_INSTANCE_HANDLE: int | None = None


def get_app_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        root = str(Path.home() / "AppData" / "Local")
    return Path(root) / APP_DIR_NAME


def get_config_path() -> Path:
    return get_app_dir() / CONFIG_FILE_NAME


def get_wrapper_path(app_dir: Path) -> Path:
    return app_dir / WRAPPER_NAME


def get_manifest_path(app_dir: Path) -> Path:
    return app_dir / MANIFEST_NAME


def _is_windows() -> bool:
    return os.name == "nt"


def _get_kernel32() -> Any:
    return ctypes.windll.kernel32


def acquire_single_instance(name: str = APP_KEY) -> bool:
    if not _is_windows():
        return True
    global _SINGLE_INSTANCE_HANDLE
    if _SINGLE_INSTANCE_HANDLE is not None:
        return True

    kernel32 = _get_kernel32()
    try:
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
    except Exception:
        pass
    handle = kernel32.CreateMutexW(None, True, f"Local\\{name}")
    if not handle:
        try:
            last_error = kernel32.GetLastError()
        except Exception:
            last_error = None
        log_event("warning", "single_instance_mutex_failed", error=last_error)
        return True
    try:
        last_error = kernel32.GetLastError()
    except Exception:
        last_error = 0
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        try:
            kernel32.CloseHandle(handle)
        except Exception:
            pass
        return False
    _SINGLE_INSTANCE_HANDLE = int(handle)
    return True
