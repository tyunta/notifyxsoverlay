import json

import notifyxsoverlay.config as config
from notifyxsoverlay.config import default_config, load_config, normalize_config, reset_learning_state, save_config


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_save_config_creates_backup(tmp_path):
    path = tmp_path / "config.json"
    data1 = default_config()
    save_config(path, data1)

    data2 = default_config()
    data2["filters"]["allow"] = ["example.app"]
    save_config(path, data2)

    backup = path.with_suffix(path.suffix + ".bak")
    assert backup.exists()
    backup_data = json.loads(backup.read_text(encoding="utf-8"))
    assert backup_data["filters"]["allow"] == data1["filters"]["allow"]


def test_load_config_restores_from_backup(tmp_path):
    path = tmp_path / "config.json"
    backup = path.with_suffix(path.suffix + ".bak")
    _write_json(backup, {"filters": {"allow": ["restored.app"]}})
    path.write_text("{bad json", encoding="utf-8")

    config = load_config(path)

    assert config["filters"]["allow"] == ["restored.app"]
    assert path.exists()


def test_load_config_reads_json(tmp_path):
    path = tmp_path / "config.json"
    _write_json(path, {"filters": {"allow": ["from.json"]}})
    loaded = load_config(path)
    assert loaded["filters"]["allow"] == ["from.json"]


def test_load_config_renames_corrupt_and_uses_fallback(tmp_path):
    path = tmp_path / "config.json"
    backup = path.with_suffix(path.suffix + ".bak")
    path.write_text("{bad json", encoding="utf-8")
    backup.write_text("{bad json", encoding="utf-8")

    fallback = default_config()
    fallback["filters"]["allow"] = ["fallback.app"]

    config = load_config(path, fallback=fallback)

    corrupt = path.with_suffix(path.suffix + ".corrupt")
    assert config is fallback
    assert corrupt.exists()


def test_load_config_missing_returns_default(tmp_path):
    path = tmp_path / "config.json"
    loaded = load_config(path)
    assert loaded == default_config()


def test_load_config_non_dict_json_renames_and_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    loaded = load_config(path)

    corrupt = path.with_suffix(path.suffix + ".corrupt")
    assert loaded == default_config()
    assert corrupt.exists()


def test_load_config_restore_logs_failure(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    backup = path.with_suffix(path.suffix + ".bak")
    _write_json(backup, {"filters": {"allow": ["restored.app"]}})
    path.write_text("{bad json", encoding="utf-8")

    logged = []

    def capture(level, event, **_fields):
        logged.append((level, event))

    def boom(*_args, **_kwargs):
        raise OSError("nope")

    monkeypatch.setattr(config, "_write_text_atomic", boom)
    monkeypatch.setattr(config, "log_event", capture)

    loaded = load_config(path)

    assert loaded["filters"]["allow"] == ["restored.app"]
    assert ("error", "config_restore_failed") in logged


def test_load_config_corrupt_rename_failure(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{bad json", encoding="utf-8")

    logged = []

    def capture(level, event, **_fields):
        logged.append((level, event))

    def boom(self, target):
        raise OSError("nope")

    monkeypatch.setattr(config, "log_event", capture)
    monkeypatch.setattr(config.Path, "replace", boom)

    loaded = load_config(path)

    assert loaded == default_config()
    assert ("warning", "config_corrupt_rename_failed") in logged


def test_normalize_config_migrates_and_sanitizes():
    data = {
        "filters": {"allow": "not-list", "block": "also-not-list"},
        "learning": {
            "pending": "nope",
            "shown_session": "nope",
            "shown_today": {"app": "2024-01-01"},
        },
        "xs_overlay": {"notification_timeout_seconds": 5.0},
        "poll_interval_seconds": 2.0,
        "extra": 1,
    }

    normalized = normalize_config(data)

    assert normalized["filters"]["allow"] == []
    assert normalized["filters"]["block"] == []
    assert normalized["learning"]["pending"] == {}
    assert normalized["learning"]["shown_session"] == {"app": "2024-01-01"}
    assert "shown_today" not in normalized["learning"]
    assert normalized["extra"] == 1


def test_normalize_config_defaults_shown_session():
    data = {"learning": {"shown_session": "nope", "shown_today": "nope"}}
    normalized = normalize_config(data)
    assert normalized["learning"]["shown_session"] == {}


def test_normalize_config_adds_steamvr_defaults():
    normalized = normalize_config({})
    assert normalized["steamvr"]["exit_on_shutdown"] is True


def test_reset_learning_state_resets_once():
    config_data = default_config()
    config_data["learning"]["shown_session"] = {"app": "time"}

    changed = reset_learning_state(config_data, "session-1")
    assert changed is True
    assert config_data["learning"]["shown_session"] == {}

    changed_again = reset_learning_state(config_data, "session-1")
    assert changed_again is False


def test_save_config_throttles_log(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise OSError("nope")

    logged = []

    def capture(level, event, **_fields):
        logged.append((level, event))

    monkeypatch.setattr(config, "_write_text_atomic", boom)
    monkeypatch.setattr(config, "log_event", capture)
    monkeypatch.setattr(config.time, "time", lambda: 100.0)

    path = tmp_path / "config.json"
    config._SAVE_FAIL_STATE["last_log_at"] = 0.0
    config._SAVE_FAIL_STATE["interval_seconds"] = 30.0

    save_config(path, default_config())
    save_config(path, default_config())

    assert logged == [("warning", "config_save_failed")]


def test_write_text_atomic_logs_backup_failure(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text("old", encoding="utf-8")

    logged = []

    def capture(level, event, **_fields):
        logged.append((level, event))

    def boom(*_args, **_kwargs):
        raise OSError("nope")

    monkeypatch.setattr(config, "log_event", capture)
    monkeypatch.setattr(config.shutil, "copyfile", boom)

    config._write_text_atomic(path, "new", backup=True)

    assert path.read_text(encoding="utf-8") == "new"
    assert ("warning", "config_backup_failed") in logged
