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


def test_acquire_single_instance_non_windows(monkeypatch):
    monkeypatch.setattr(app, "_is_windows", lambda: False)
    app._SINGLE_INSTANCE_HANDLE = None
    assert app.acquire_single_instance() is True


def test_acquire_single_instance_detects_existing(monkeypatch):
    class DummyKernel:
        def __init__(self):
            self.closed = False

        def CreateMutexW(self, *_args):
            return 1

        def GetLastError(self):
            return 183

        def CloseHandle(self, _handle):
            self.closed = True

    dummy = DummyKernel()
    monkeypatch.setattr(app, "_is_windows", lambda: True)
    monkeypatch.setattr(app, "_get_kernel32", lambda: dummy)
    app._SINGLE_INSTANCE_HANDLE = None
    assert app.acquire_single_instance() is False
    assert dummy.closed is True


def test_acquire_single_instance_ok(monkeypatch):
    class DummyKernel:
        def CreateMutexW(self, *_args):
            return 1

        def GetLastError(self):
            return 0

    dummy = DummyKernel()
    monkeypatch.setattr(app, "_is_windows", lambda: True)
    monkeypatch.setattr(app, "_get_kernel32", lambda: dummy)
    app._SINGLE_INSTANCE_HANDLE = None
    assert app.acquire_single_instance() is True
    assert app._SINGLE_INSTANCE_HANDLE == 1
