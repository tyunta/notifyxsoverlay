from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .app import (
    APP_COMMAND,
    APP_KEY,
    APP_NAME,
    DEFAULT_REPO,
    get_app_dir,
    get_manifest_path,
    get_wrapper_path,
)
from .bridge import run_bridge
from .log import log_event


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


def build_manifest(binary_path: Path, arguments: str) -> dict[str, Any]:
    return {
        "source": "builtin",
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


def build_uvx_arguments(repo: str, quote_repo: bool = True) -> str:
    repo_value = f'"{repo}"' if quote_repo else repo
    return f"--refresh --from {repo_value} {APP_COMMAND} run"


def get_cmd_exe() -> Path:
    comspec = os.environ.get("ComSpec")
    if comspec:
        return Path(comspec)
    return Path(r"C:\Windows\System32\cmd.exe")


def build_manifest_variants(
    uvx_exe: Path,
    repo: str,
    wrapper_path: Path,
) -> list[tuple[str, Path, str]]:
    args_plain = build_uvx_arguments(repo, quote_repo=False)
    args_quoted = build_uvx_arguments(repo, quote_repo=True)
    variants: list[tuple[str, Path, str]] = []
    if uvx_exe.suffix.lower() == ".exe":
        variants.append(("uvx_direct", uvx_exe, args_plain))
        variants.append(("uvx_direct_quoted", uvx_exe, args_quoted))
    cmd_exe = get_cmd_exe()
    variants.append(("cmd_uvx_plain", cmd_exe, f'/c "{uvx_exe}" {args_plain}'))
    variants.append(("cmd_uvx_quoted", cmd_exe, f'/c "{uvx_exe}" {args_quoted}'))
    variants.append(("cmd_wrapper", cmd_exe, f'/c "{wrapper_path}"'))
    return variants


def write_manifest_variant(
    manifest_path: Path,
    binary_path: Path,
    arguments: str,
) -> None:
    manifest = build_manifest(binary_path, arguments)
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


def get_vrapp_method(apps: Any, *names: str) -> Any | None:
    for name in names:
        method = getattr(apps, name, None)
        if callable(method):
            return method
    return None


def _normalize_method_name(name: str) -> str:
    return name.replace("_", "").lower()


def find_vrapp_method(apps: Any, *names: str) -> Any | None:
    method = get_vrapp_method(apps, *names)
    if method is not None:
        return method
    targets = {_normalize_method_name(name) for name in names}
    for attr in dir(apps):
        normalized = _normalize_method_name(attr)
        if normalized in targets:
            candidate = getattr(apps, attr, None)
            if callable(candidate):
                return candidate
    return None


def find_vrapp_method_by_tokens(apps: Any, *tokens: str) -> Any | None:
    tokens_normalized = [_normalize_method_name(token) for token in tokens]
    for attr in dir(apps):
        normalized = _normalize_method_name(attr)
        if all(token in normalized for token in tokens_normalized):
            candidate = getattr(apps, attr, None)
            if callable(candidate):
                return candidate
    return None


def summarize_vrapp_methods(apps: Any) -> str:
    candidates = []
    for name in dir(apps):
        lowered = name.lower()
        if "manifest" in lowered or "application" in lowered or "autolaunch" in lowered:
            candidates.append(name)
    candidates = sorted(set(candidates))
    if not candidates:
        return ""
    if len(candidates) > 20:
        return ", ".join(candidates[:20]) + ", ..."
    return ", ".join(candidates)


def call_vrapp_method(
    apps: Any,
    names: tuple[str, ...],
    tokens: tuple[str, ...] | None,
    *args: Any,
) -> int | None:
    method = find_vrapp_method(apps, *names)
    if method is None and tokens is not None:
        method = find_vrapp_method_by_tokens(apps, *tokens)
    if method is None:
        return None
    result = method(*args)
    if result is None:
        return 0
    return int(result)


def register_manifest(
    manifest_path: Path,
    auto_launch: bool,
    variants: list[tuple[str, Path, str]],
) -> None:
    openvr = with_openvr()
    if openvr is None:
        raise RuntimeError("openvr module not available")

    openvr.init(openvr.VRApplication_Utility)
    try:
        apps = openvr.VRApplications()
        remove_err = call_vrapp_method(
            apps,
            ("RemoveApplicationManifest", "remove_application_manifest", "removeApplicationManifest"),
            ("remove", "application", "manifest"),
            str(manifest_path),
        )
        if remove_err is None:
            log_event(
                "warning",
                "steamvr_install_skip",
                action="RemoveApplicationManifest",
                error="method_not_available",
            )
        invalid_error = getattr(openvr, "ApplicationError_InvalidManifest", None)
        last_invalid: Exception | None = None
        for variant, binary_path, arguments in variants:
            write_manifest_variant(manifest_path, binary_path, arguments)
            try:
                add_err = call_vrapp_method(
                    apps,
                    ("AddApplicationManifest", "add_application_manifest", "addApplicationManifest"),
                    ("add", "application", "manifest"),
                    str(manifest_path),
                    False,
                )
            except Exception as exc:  # pragma: no cover - depends on OpenVR binding
                if type(exc).__name__ == "ApplicationError_InvalidManifest":
                    log_event(
                        "warning",
                        "steamvr_manifest_rejected",
                        variant=variant,
                        binary_path=str(binary_path),
                        arguments=arguments,
                        error_type=type(exc).__name__,
                        error_repr=repr(exc),
                    )
                    last_invalid = exc
                    continue
                raise
            if add_err is None:
                available = summarize_vrapp_methods(apps)
                if available:
                    log_event(
                        "warning",
                        "steamvr_install_methods",
                        available=available,
                    )
                raise RuntimeError("AddApplicationManifest not available")
            if int(add_err) != 0:
                if invalid_error is not None and int(add_err) == int(invalid_error):
                    log_event(
                        "warning",
                        "steamvr_manifest_rejected",
                        variant=variant,
                        binary_path=str(binary_path),
                        arguments=arguments,
                        error=int(add_err),
                    )
                    last_invalid = RuntimeError(f"AddApplicationManifest failed: {add_err}")
                    continue
                raise RuntimeError(f"AddApplicationManifest failed: {add_err}")
            auto_err = call_vrapp_method(
                apps,
                ("SetApplicationAutoLaunch", "set_application_auto_launch", "setApplicationAutoLaunch"),
                ("set", "application", "auto", "launch"),
                APP_KEY,
                auto_launch,
            )
            if auto_err is None:
                raise RuntimeError("SetApplicationAutoLaunch not available")
            if int(auto_err) != 0:
                raise RuntimeError(f"SetApplicationAutoLaunch failed: {auto_err}")
            log_event(
                "info",
                "steamvr_manifest_selected",
                variant=variant,
                binary_path=str(binary_path),
            )
            return
        if last_invalid is not None:
            raise last_invalid
        raise RuntimeError("AddApplicationManifest failed for all variants")
    finally:
        openvr.shutdown()


def unregister_manifest(manifest_path: Path, allow_missing: bool = False) -> None:
    openvr = with_openvr()
    if openvr is None:
        raise RuntimeError("openvr module not available")

    openvr.init(openvr.VRApplication_Utility)
    try:
        apps = openvr.VRApplications()
        auto_err = call_vrapp_method(
            apps,
            ("SetApplicationAutoLaunch", "set_application_auto_launch", "setApplicationAutoLaunch"),
            ("set", "application", "auto", "launch"),
            APP_KEY,
            False,
        )
        if auto_err is None:
            log_event(
                "warning",
                "steamvr_uninstall_skip",
                action="SetApplicationAutoLaunch",
                error="method_not_available",
            )
        elif int(auto_err) != 0 and not allow_missing:
            raise RuntimeError(f"SetApplicationAutoLaunch failed: {auto_err}")
        elif int(auto_err) != 0 and allow_missing:
            log_event(
                "warning",
                "steamvr_uninstall_skip",
                action="SetApplicationAutoLaunch",
                error=int(auto_err),
            )
        remove_err = call_vrapp_method(
            apps,
            ("RemoveApplicationManifest", "remove_application_manifest", "removeApplicationManifest"),
            ("remove", "application", "manifest"),
            str(manifest_path),
        )
        if remove_err is None:
            log_event(
                "warning",
                "steamvr_uninstall_skip",
                action="RemoveApplicationManifest",
                error="method_not_available",
            )
        elif int(remove_err) != 0 and not allow_missing:
            raise RuntimeError(f"RemoveApplicationManifest failed: {remove_err}")
        elif int(remove_err) != 0 and allow_missing:
            log_event(
                "warning",
                "steamvr_uninstall_skip",
                action="RemoveApplicationManifest",
                error=int(remove_err),
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
    variants = build_manifest_variants(Path(uvx_exe), repo, wrapper_path)

    try:
        register_manifest(manifest_path, auto_launch=True, variants=variants)
        log_event("info", "steamvr_install_ok", app_key=APP_KEY, manifest=str(manifest_path))
        return 0
    except Exception as exc:
        error_payload = {
            "error": str(exc),
            "error_type": type(exc).__name__,
            "error_repr": repr(exc),
            "manifest": str(manifest_path),
            "variants": [variant for variant, _, _ in variants],
        }
        log_event(
            "error",
            "steamvr_install_failed",
            **error_payload,
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
        error_payload = {
            "error": str(exc),
            "error_type": type(exc).__name__,
            "error_repr": repr(exc),
        }
        log_event(
            "error",
            "steamvr_uninstall_failed",
            **error_payload,
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
    try:
        return asyncio.run(run_bridge(ws_url=args.ws_url, poll_interval=args.poll_interval))
    except KeyboardInterrupt:
        log_event("info", "run_stop")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_COMMAND)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the notification bridge")
    run.add_argument(
        "--ws-url",
        default=None,
        help="Override XSOverlay WebSocket URL",
    )
    run.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Notification polling interval in seconds",
    )
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
