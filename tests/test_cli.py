import builtins
import json
import os
import sys
import types
from pathlib import Path

import pytest

from notifyxsoverlay import cli


def test_normalize_repo():
    assert cli.normalize_repo("git+https://example.com/repo") == "git+https://example.com/repo"
    assert cli.normalize_repo("https://example.com/repo") == "git+https://example.com/repo"
    assert cli.normalize_repo("local/path") == "local/path"


def test_build_uvx_arguments_quote():
    repo = "git+https://example.com/repo"
    quoted = cli.build_uvx_arguments(repo, quote_repo=True)
    unquoted = cli.build_uvx_arguments(repo, quote_repo=False)
    assert f'--from "{repo}"' in quoted
    assert f"--from {repo}" in unquoted


def test_get_cmd_exe_prefers_comspec(monkeypatch):
    monkeypatch.setenv("ComSpec", r"C:\Temp\cmd.exe")
    assert str(cli.get_cmd_exe()) == r"C:\Temp\cmd.exe"


def test_get_cmd_exe_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("ComSpec", raising=False)
    assert str(cli.get_cmd_exe()) == r"C:\Windows\System32\cmd.exe"


def test_resolve_uvx_path_explicit(monkeypatch):
    monkeypatch.setattr(cli.Path, "exists", lambda _self: True)
    path, found = cli.resolve_uvx_path("C:/bin/uvx.exe")
    assert Path(path) == Path("C:/bin/uvx.exe")
    assert found is True


def test_resolve_uvx_path_expands_env(monkeypatch):
    monkeypatch.setenv("UVX_HOME", "C:/bin")
    expanded = os.path.expandvars("%UVX_HOME%/uvx.exe")
    expanded_path = Path(expanded)

    def fake_exists(self):
        return self == expanded_path

    monkeypatch.setattr(cli.Path, "exists", fake_exists)
    path, found = cli.resolve_uvx_path("%UVX_HOME%/uvx.exe")
    assert Path(path) == expanded_path
    assert found is True


def test_resolve_uvx_path_explicit_uses_which(monkeypatch):
    monkeypatch.setattr(cli.Path, "exists", lambda _self: False)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "C:/bin/uvx.exe")
    path, found = cli.resolve_uvx_path("uvx.exe")
    assert path == "C:/bin/uvx.exe"
    assert found is True


def test_resolve_uvx_path_explicit_not_found(monkeypatch):
    monkeypatch.setattr(cli.Path, "exists", lambda _self: False)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    path, found = cli.resolve_uvx_path("C:/bin/uvx.exe")
    assert path == "C:/bin/uvx.exe"
    assert found is False


def test_build_manifest_overlay_flag():
    manifest = cli.build_manifest(Path("C:/bin/tool.exe"), "--arg", include_overlay=True)
    app_entry = manifest["applications"][0]
    assert app_entry["is_dashboard_overlay"] is True


def test_build_manifest_minimal_no_overlay():
    manifest = cli.build_manifest(Path("C:/bin/tool.exe"), "--arg", include_overlay=False)
    app_entry = manifest["applications"][0]
    assert "is_dashboard_overlay" not in app_entry


def test_build_manifest_variants_exe():
    uvx_exe = Path("C:/bin/uvx.exe")
    wrapper_path = Path("C:/temp/wrapper.cmd")
    variants = cli.build_manifest_variants(uvx_exe, "git+https://example.com/repo", wrapper_path)
    names = {name for name, _, _, _ in variants}
    assert "uvx_direct_overlay" in names
    assert "cmd_wrapper_minimal" in names


def test_build_manifest_variants_non_exe():
    uvx_exe = Path("C:/bin/uvx.cmd")
    wrapper_path = Path("C:/temp/wrapper.cmd")
    variants = cli.build_manifest_variants(uvx_exe, "git+https://example.com/repo", wrapper_path)
    names = {name for name, _, _, _ in variants}
    assert "uvx_direct_overlay" not in names
    assert "cmd_wrapper_overlay" in names


def test_write_manifest_variant(tmp_path):
    manifest_path = tmp_path / "app.vrmanifest"
    cli.write_manifest_variant(manifest_path, Path("C:/bin/tool.exe"), "--arg", include_overlay=True)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["source"] == "builtin"
    assert data["applications"][0]["binary_path_windows"].endswith("tool.exe")


def test_write_wrapper_contains_refresh_and_fallback(tmp_path):
    wrapper_path = tmp_path / "notifyxsoverlay.cmd"
    cli.write_wrapper(wrapper_path, "git+https://example.com/repo", "C:/bin/uvx.exe")
    content = wrapper_path.read_text(encoding="utf-8")
    assert "--refresh --from" in content
    assert "if errorlevel 1" in content


def test_write_wrapper_escapes_percent_and_quote(tmp_path):
    wrapper_path = tmp_path / "notifyxsoverlay.cmd"
    cli.write_wrapper(
        wrapper_path,
        'git+https://example.com/%TEMP%/"repo"?a=1&b=2',
        'C:/bin/u"vx.exe',
    )
    content = wrapper_path.read_text(encoding="utf-8")
    assert "%%TEMP%%" in content
    assert '""repo""' in content
    assert 'u""vx.exe' in content
    assert "^&b=2" in content


def test_write_wrapper_escapes_parens_and_pipe(tmp_path):
    wrapper_path = tmp_path / "notifyxsoverlay.cmd"
    cli.write_wrapper(
        wrapper_path,
        "git+https://example.com/(x)|y",
        "C:/bin/uvx.exe",
    )
    content = wrapper_path.read_text(encoding="utf-8")
    assert "^(x^)^|y" in content


def test_find_vrapp_method_by_tokens():
    class Dummy:
        def setApplicationAutoLaunch(self):  # pragma: no cover - exercised via getattr
            return 0

    method = cli.find_vrapp_method_by_tokens(Dummy(), "set", "application", "auto", "launch")
    assert callable(method)


def test_find_vrapp_method_normalized():
    class Dummy:
        def addApplicationManifest(self):  # pragma: no cover - exercised via getattr
            return 0

    method = cli.find_vrapp_method(Dummy(), "add_application_manifest")
    assert callable(method)


def test_find_vrapp_method_returns_none_when_missing():
    class Dummy:
        pass

    assert cli.find_vrapp_method(Dummy(), "missing_method") is None


def test_summarize_vrapp_methods_empty():
    class Dummy:
        pass

    assert cli.summarize_vrapp_methods(Dummy()) == ""


def test_summarize_vrapp_methods_small_list():
    dummy = types.SimpleNamespace()
    setattr(dummy, "AddApplicationManifest", lambda: None)
    setattr(dummy, "SetApplicationAutoLaunch", lambda: None)

    summary = cli.summarize_vrapp_methods(dummy)
    assert "AddApplicationManifest" in summary
    assert "SetApplicationAutoLaunch" in summary
    assert summary.endswith("...") is False


def test_summarize_vrapp_methods_limits():
    class Dummy:
        def add_application_manifest(self):  # pragma: no cover - accessed via dir
            return 0

    # Populate many attributes to exercise truncation
    dummy = Dummy()
    for i in range(30):
        setattr(dummy, f"application_method_{i}", lambda: None)
    summary = cli.summarize_vrapp_methods(dummy)
    assert summary.endswith("...") or "application_method_0" in summary


def test_call_vrapp_method_returns_zero_on_none():
    class Dummy:
        def add_application_manifest(self, *_args):
            return None

    result = cli.call_vrapp_method(
        Dummy(),
        ("add_application_manifest",),
        ("add", "application", "manifest"),
        "path",
        False,
    )
    assert result == 0


def test_call_vrapp_method_returns_int():
    class Dummy:
        def add_application_manifest(self, *_args):
            return 2

    result = cli.call_vrapp_method(
        Dummy(),
        ("add_application_manifest",),
        ("add", "application", "manifest"),
        "path",
        False,
    )
    assert result == 2


def test_call_vrapp_method_returns_none_when_missing():
    class Dummy:
        pass

    result = cli.call_vrapp_method(
        Dummy(),
        ("missing_method",),
        ("missing", "method"),
    )
    assert result is None


def test_resolve_uvx_path(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "C:/bin/uvx.exe")
    path, found = cli.resolve_uvx_path(None)
    assert path.endswith("uvx.exe")
    assert found is True
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    path, found = cli.resolve_uvx_path(None)
    assert path == "uvx"
    assert found is False


def test_with_openvr_returns_none_on_import_error(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openvr":
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert cli.with_openvr() is None


def test_with_openvr_returns_module(monkeypatch):
    dummy = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "openvr", dummy)
    assert cli.with_openvr() is dummy


def test_build_parser_parses_run():
    parser = cli.build_parser()
    args = parser.parse_args(["run"])
    assert args.command == "run"
    assert args.ws_url is None
    assert args.poll_interval is None


def test_cmd_run_uses_run_bridge(monkeypatch):
    async def fake_run_bridge(ws_url=None, poll_interval=None):
        return 0

    monkeypatch.setattr(cli, "run_bridge", fake_run_bridge)
    args = types.SimpleNamespace(ws_url=None, poll_interval=None)
    assert cli.cmd_run(args) == 0


def test_cmd_run_logs_on_keyboard_interrupt(monkeypatch):
    logged = []

    def fake_run(_coro):
        raise KeyboardInterrupt

    def capture(level, event, **_fields):
        logged.append((level, event))

    monkeypatch.setattr(cli.asyncio, "run", fake_run)
    monkeypatch.setattr(cli, "run_bridge", lambda **_kwargs: "ignored")
    monkeypatch.setattr(cli, "log_event", capture)
    args = types.SimpleNamespace(ws_url=None, poll_interval=None)
    assert cli.cmd_run(args) == 0
    assert ("info", "run_stop") in logged


def test_main_runs_command(monkeypatch):
    monkeypatch.setattr(cli, "cmd_run", lambda _args: 7)
    assert cli.main(["run"]) == 7


def test_register_manifest_raises_when_openvr_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "with_openvr", lambda: None)
    with pytest.raises(RuntimeError, match="openvr module not available"):
        cli.register_manifest(
            tmp_path / "app.vrmanifest",
            auto_launch=True,
            variants=[],
        )


def test_unregister_manifest_raises_when_openvr_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "with_openvr", lambda: None)
    with pytest.raises(RuntimeError, match="openvr module not available"):
        cli.unregister_manifest(tmp_path / "app.vrmanifest")


def test_cmd_install_success(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "get_wrapper_path", lambda app_dir: app_dir / "notifyxsoverlay.cmd")
    monkeypatch.setattr(cli, "get_manifest_path", lambda app_dir: app_dir / "notifyxsoverlay.vrmanifest")
    monkeypatch.setattr(cli, "resolve_uvx_path", lambda _path: ("C:/bin/uvx.exe", True))
    monkeypatch.setattr(cli, "register_manifest", lambda *_args, **_kwargs: None)

    args = types.SimpleNamespace(repo="https://example.com/repo", uvx_path=None)
    assert cli.cmd_install(args) == 0
    assert (tmp_path / "notifyxsoverlay.cmd").exists()


def test_cmd_install_uvx_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "resolve_uvx_path", lambda _path: ("uvx", False))
    monkeypatch.setattr(cli, "log_event", lambda *_args, **_kwargs: None)

    args = types.SimpleNamespace(repo="https://example.com/repo", uvx_path=None)
    assert cli.cmd_install(args) == 1


def test_cmd_install_register_failure_logs(monkeypatch, tmp_path):
    logged = []

    def capture(level, event, **_fields):
        logged.append((level, event))

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "get_wrapper_path", lambda app_dir: app_dir / "notifyxsoverlay.cmd")
    monkeypatch.setattr(cli, "get_manifest_path", lambda app_dir: app_dir / "notifyxsoverlay.vrmanifest")
    monkeypatch.setattr(cli, "resolve_uvx_path", lambda _path: ("C:/bin/uvx.exe", True))
    monkeypatch.setattr(cli, "register_manifest", boom)
    monkeypatch.setattr(cli, "log_event", capture)

    args = types.SimpleNamespace(repo="https://example.com/repo", uvx_path=None)
    assert cli.cmd_install(args) == 1
    assert ("error", "steamvr_install_failed") in logged


def test_cmd_uninstall_removes_files(monkeypatch, tmp_path):
    app_dir = tmp_path
    wrapper_path = app_dir / "notifyxsoverlay.cmd"
    manifest_path = app_dir / "notifyxsoverlay.vrmanifest"
    wrapper_path.write_text("wrapper", encoding="utf-8")
    manifest_path.write_text("manifest", encoding="utf-8")

    monkeypatch.setattr(cli, "get_app_dir", lambda: app_dir)
    monkeypatch.setattr(cli, "get_wrapper_path", lambda _app_dir: wrapper_path)
    monkeypatch.setattr(cli, "get_manifest_path", lambda _app_dir: manifest_path)
    monkeypatch.setattr(cli, "unregister_manifest", lambda *_args, **_kwargs: None)

    args = types.SimpleNamespace()
    assert cli.cmd_uninstall(args) == 0
    assert not wrapper_path.exists()
    assert not manifest_path.exists()
    assert not app_dir.exists()


def test_cmd_uninstall_manifest_missing_logs(monkeypatch, tmp_path):
    logged = []

    def capture(level, event, **_fields):
        logged.append((level, event))

    monkeypatch.setattr(cli, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "get_wrapper_path", lambda app_dir: app_dir / "notifyxsoverlay.cmd")
    monkeypatch.setattr(cli, "get_manifest_path", lambda app_dir: app_dir / "notifyxsoverlay.vrmanifest")
    monkeypatch.setattr(cli, "unregister_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "log_event", capture)

    args = types.SimpleNamespace()
    assert cli.cmd_uninstall(args) == 0
    assert ("warning", "manifest_missing") in logged


def test_cmd_uninstall_unregister_failure_logs(monkeypatch, tmp_path):
    logged = []

    def capture(level, event, **_fields):
        logged.append((level, event))

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    wrapper_path = tmp_path / "notifyxsoverlay.cmd"
    manifest_path = tmp_path / "notifyxsoverlay.vrmanifest"
    wrapper_path.write_text("wrapper", encoding="utf-8")
    manifest_path.write_text("manifest", encoding="utf-8")

    monkeypatch.setattr(cli, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "get_wrapper_path", lambda _app_dir: wrapper_path)
    monkeypatch.setattr(cli, "get_manifest_path", lambda _app_dir: manifest_path)
    monkeypatch.setattr(cli, "unregister_manifest", boom)
    monkeypatch.setattr(cli, "log_event", capture)

    args = types.SimpleNamespace()
    assert cli.cmd_uninstall(args) == 1
    assert ("error", "steamvr_uninstall_failed") in logged


def test_cmd_uninstall_rmdir_failure_ignored(monkeypatch, tmp_path):
    wrapper_path = tmp_path / "notifyxsoverlay.cmd"
    manifest_path = tmp_path / "notifyxsoverlay.vrmanifest"
    extra_path = tmp_path / "keep.txt"
    wrapper_path.write_text("wrapper", encoding="utf-8")
    manifest_path.write_text("manifest", encoding="utf-8")
    extra_path.write_text("keep", encoding="utf-8")

    monkeypatch.setattr(cli, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "get_wrapper_path", lambda _app_dir: wrapper_path)
    monkeypatch.setattr(cli, "get_manifest_path", lambda _app_dir: manifest_path)
    monkeypatch.setattr(cli, "unregister_manifest", lambda *_args, **_kwargs: None)

    args = types.SimpleNamespace()
    assert cli.cmd_uninstall(args) == 0
    assert extra_path.exists()
