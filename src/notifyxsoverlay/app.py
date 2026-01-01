# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ちゅんた

from __future__ import annotations

import os
from pathlib import Path

APP_KEY = "com.tyunta.notifyxsoverlay"
APP_NAME = "NotifyXSOverlay"
APP_DIR_NAME = "NotifyXSOverlay"
APP_COMMAND = "notifyxsoverlay"
WRAPPER_NAME = "notifyxsoverlay.cmd"
MANIFEST_NAME = "notifyxsoverlay.vrmanifest"
DEFAULT_REPO = "git+https://github.com/tyunta/notifyxsoverlay"
CONFIG_FILE_NAME = "config.json"


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
