from __future__ import annotations

import argparse
import json
import os
import sys
import shutil
import threading
from pathlib import Path
from typing import Any

APP_KEY = "com.tyunta.notifyxsoverlay"
APP_NAME = "NotifyXSOverlay"
APP_DIR_NAME = "NotifyXSOverlay"
APP_COMMAND = "notifyxsoverlay"
WRAPPER_NAME = "notifyxsoverlay.cmd"
MANIFEST_NAME = "notifyxsoverlay.vrmanifest"
DEFAULT_REPO = "git+https://github.com/tyunta/notifyxsoverlay"


def log_event(level: str, event: str, **fields: Any) -> None:
    payload = {"level": level, "event": event}
    payload.update(fields)
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)


def get_app_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        root = str(Path.home() / "AppData" / "Local")
    return Path(root) / APP_DIR_NAME


def get_wrapper_path(app_dir: Path) -> Path:
    return app_dir / WRAPPER_NAME


def get_manifest_path(app_dir: Path) -> Path:
    return app_dir / MANIFEST_NAME




def normalize_repo(repo: str) -> str:
    repo = repo.strip()
    if repo.startswith("git+"):
        return repo
    if repo.startswith("http://") or repo.startswith("https://"):
        return f"git+{repo}"
    return repo


def resolve_uvx_path(explicit_path: str | None) -> tuple[str, bool]:
    if explicit_path:
        return explicit_path, True
    detected = shutil.which("uvx")
    if detected:
        return detected, True
    return "uvx", False


def write_wrapper(wrapper_path: Path, repo: str, uvx_exe: str) -> None:
    wrapper_content = (
        "@echo off\n"
        "setlocal\n"
        f"\"{uvx_exe}\" --refresh --from \"{repo}\" {APP_COMMAND} run\n"
        "if errorlevel 1 (\n"
        f"  \"{uvx_exe}\" --from \"{repo}\" {APP_COMMAND} run\n"
        ")\n"
    )
    wrapper_path.write_text(wrapper_content, encoding="utf-8")


def get_cmd_exe() -> Path:
    comspec = os.environ.get("ComSpec")
    if comspec:
        return Path(comspec)
    return Path(r"C:\Windows\System32\cmd.exe")


def build_manifest(binary_path: Path, arguments: str) -> dict[str, Any]:
    return {
        "source": APP_COMMAND,
        "applications": [
            {
                "app_key": APP_KEY,
                "launch_type": "binary",
                "binary_path_windows": str(binary_path),
                "arguments": arguments,
                "is_dashboard_overlay": True,
                "strings": {
                    "en_us": {
                        "name": APP_NAME,
                        "description": "Bridge Windows notifications to XSOverlay.",
                    }
                },
            }
        ],
    }


def write_manifest(manifest_path: Path, wrapper_path: Path) -> None:
    cmd_exe = get_cmd_exe()
    args = f'/c "{wrapper_path}"'
    manifest = build_manifest(cmd_exe, args)
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def with_openvr() -> Any | None:
    try:
        import openvr  # type: ignore

        return openvr
    except Exception:
        return None


def register_manifest(manifest_path: Path, auto_launch: bool) -> None:
    openvr = with_openvr()
    if openvr is None:
        raise RuntimeError("openvr module not available")

    openvr.init(openvr.VRApplication_Utility)
    try:
        apps = openvr.VRApplications()
        apps.RemoveApplicationManifest(str(manifest_path))
        err = apps.AddApplicationManifest(str(manifest_path), False)
        if int(err) != 0:
            raise RuntimeError(f"AddApplicationManifest failed: {err}")
        err = apps.SetApplicationAutoLaunch(APP_KEY, auto_launch)
        if int(err) != 0:
            raise RuntimeError(f"SetApplicationAutoLaunch failed: {err}")
    finally:
        openvr.shutdown()


def unregister_manifest(manifest_path: Path, allow_missing: bool = False) -> None:
    openvr = with_openvr()
    if openvr is None:
        raise RuntimeError("openvr module not available")

    openvr.init(openvr.VRApplication_Utility)
    try:
        apps = openvr.VRApplications()
        err = apps.SetApplicationAutoLaunch(APP_KEY, False)
        if int(err) != 0 and not allow_missing:
            raise RuntimeError(f"SetApplicationAutoLaunch failed: {err}")
        if int(err) != 0 and allow_missing:
            log_event(
                "warning",
                "steamvr_uninstall_skip",
                action="SetApplicationAutoLaunch",
                error=int(err),
            )
        err = apps.RemoveApplicationManifest(str(manifest_path))
        if int(err) != 0 and not allow_missing:
            raise RuntimeError(f"RemoveApplicationManifest failed: {err}")
        if int(err) != 0 and allow_missing:
            log_event(
                "warning",
                "steamvr_uninstall_skip",
                action="RemoveApplicationManifest",
                error=int(err),
            )
    finally:
        openvr.shutdown()


def cmd_install(args: argparse.Namespace) -> int:
    repo = normalize_repo(args.repo)
    app_dir = get_app_dir()
    app_dir.mkdir(parents=True, exist_ok=True)

    wrapper_path = get_wrapper_path(app_dir)
    manifest_path = get_manifest_path(app_dir)

    uvx_exe, uvx_found = resolve_uvx_path(args.uvx_path)
    if not uvx_found:
        log_event(
            "error",
            "uvx_not_found",
            hint="Install uv or pass --uvx-path to a valid uvx executable.",
        )
        return 1

    write_wrapper(wrapper_path, repo, uvx_exe)
    write_manifest(manifest_path, wrapper_path)

    try:
        register_manifest(manifest_path, auto_launch=True)
        log_event("info", "steamvr_install_ok", app_key=APP_KEY, manifest=str(manifest_path))
        return 0
    except Exception as exc:
        log_event(
            "error",
            "steamvr_install_failed",
            error=str(exc),
            hint="Start SteamVR and retry, or enable auto-launch manually in SteamVR settings.",
        )
        return 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    app_dir = get_app_dir()
    wrapper_path = get_wrapper_path(app_dir)
    manifest_path = get_manifest_path(app_dir)
    manifest_missing = not manifest_path.exists()
    if manifest_missing:
        log_event("warning", "manifest_missing", manifest=str(manifest_path))

    error: Exception | None = None
    try:
        unregister_manifest(manifest_path, allow_missing=manifest_missing)
        log_event(
            "info",
            "steamvr_uninstall_ok",
            app_key=APP_KEY,
            manifest=str(manifest_path),
            manifest_missing=manifest_missing,
        )
    except Exception as exc:
        log_event(
            "error",
            "steamvr_uninstall_failed",
            error=str(exc),
            hint="Start SteamVR and retry, or remove the manifest manually.",
        )
        error = exc

    if wrapper_path.exists():
        wrapper_path.unlink()
    if manifest_path.exists():
        manifest_path.unlink()

    try:
        app_dir.rmdir()
    except OSError:
        pass

    return 0 if error is None else 1


def cmd_run(args: argparse.Namespace) -> int:
    log_event("info", "run_start", app_key=APP_KEY)
    log_event("info", "run_note", detail="Notification bridge is not implemented yet.")

    stop_event = threading.Event()
    try:
        stop_event.wait()
    except KeyboardInterrupt:
        log_event("info", "run_stop")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_COMMAND)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the notification bridge")
    run.set_defaults(func=cmd_run)

    install = sub.add_parser("install-steamvr", help="Register as SteamVR startup overlay")
    install.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help="Git repo to run via uvx (default: project repo)",
    )
    install.add_argument(
        "--uvx-path",
        default=None,
        help="Explicit path to uvx (default: auto-detect from PATH)",
    )
    install.set_defaults(func=cmd_install)

    uninstall = sub.add_parser("uninstall-steamvr", help="Unregister from SteamVR startup overlay")
    uninstall.set_defaults(func=cmd_uninstall)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
