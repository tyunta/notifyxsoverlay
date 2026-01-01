import json
import os
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


def test_resolve_uvx_path(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "C:/bin/uvx.exe")
    path, found = cli.resolve_uvx_path(None)
    assert path.endswith("uvx.exe")
    assert found is True
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    path, found = cli.resolve_uvx_path(None)
    assert path == "uvx"
    assert found is False
