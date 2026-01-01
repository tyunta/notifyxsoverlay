import os

from notifyxsoverlay import app


def test_get_app_dir_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app_dir = app.get_app_dir()
    assert str(app_dir).startswith(str(tmp_path))


def test_get_app_dir_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(app.Path, "home", lambda: tmp_path)
    app_dir = app.get_app_dir()
    assert str(app_dir).startswith(str(tmp_path))


def test_paths_relative_to_app_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app_dir = app.get_app_dir()
    assert app.get_config_path().parent == app_dir
    assert app.get_wrapper_path(app_dir).parent == app_dir
    assert app.get_manifest_path(app_dir).parent == app_dir
