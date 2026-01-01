from datetime import datetime

from notifyxsoverlay.bridge import (
    _build_display,
    _build_notification_payload,
    _build_ws_message,
    _call,
    _extract_app_info,
    _extract_text_elements,
    _get_attr,
    _get_toast_kind,
    _ensure_client_param,
    _access_allowed,
    _evaluate_notification,
    _notification_key,
    _prune_seen,
    _safe_notification_opacity,
    _safe_notification_timeout,
    _safe_poll_interval,
)
from notifyxsoverlay.config import default_config


def test_ensure_client_param_adds_client():
    ws_url = "ws://127.0.0.1:42070"
    assert _ensure_client_param(ws_url).endswith("?client=NotifyXSOverlay")


def test_ensure_client_param_preserves_existing():
    ws_url = "ws://127.0.0.1:42070/?client=NotifyXSOverlay"
    assert _ensure_client_param(ws_url) == ws_url


def test_get_attr_picks_first_match():
    class Dummy:
        value = "hit"

    assert _get_attr(Dummy(), "missing", "value") == "hit"


def test_call_picks_callable():
    class Dummy:
        def ping(self):
            return "pong"

    assert _call(Dummy(), "missing", "ping") == "pong"


def test_get_toast_kind_prefers_uppercase():
    class Dummy:
        TOAST = "toast"

    assert _get_toast_kind(Dummy()) == "toast"


def test_access_allowed_handles_enum_variants():
    class Dummy:
        Allowed = "ok"

    assert _access_allowed("ok", Dummy) is True


def test_extract_app_info_with_display_name():
    class Display:
        display_name = "App Name"

    class AppInfo:
        app_user_model_id = "app.id"
        display_info = Display()

    class Notification:
        app_info = AppInfo()

    app_id, display = _extract_app_info(Notification())
    assert app_id == "app.id"
    assert display == "App Name"


def test_extract_text_elements_collects_texts():
    class Element:
        def __init__(self, text):
            self.text = text

    class Binding:
        def get_text_elements(self):
            return [Element("Title"), Element("Body")]

    class Visual:
        bindings = [Binding()]

    class Notification:
        visual = Visual()

    class UserNotification:
        notification = Notification()

    assert _extract_text_elements(UserNotification()) == ["Title", "Body"]


def test_safe_notification_opacity_clamps():
    assert _safe_notification_opacity(None) == 0.6
    assert _safe_notification_opacity(0.0) == 0.0
    assert _safe_notification_opacity(0.5) == 0.5
    assert _safe_notification_opacity(-1.0) == 0.6
    assert _safe_notification_opacity(2.0) == 0.6


def test_safe_poll_interval():
    assert _safe_poll_interval(None) == 1.0
    assert _safe_poll_interval(-1.0) == 1.0
    assert _safe_poll_interval(0.2) == 0.2


def test_safe_notification_timeout():
    assert _safe_notification_timeout(None) == 3.0
    assert _safe_notification_timeout(-5.0) == 3.0
    assert _safe_notification_timeout(10.0) == 10.0


def test_block_overrides_allow():
    config = default_config()
    config["filters"]["allow"] = ["app"]
    config["filters"]["block"] = ["app"]
    allow, reason, _ = _evaluate_notification("app", "", config)
    assert allow is False
    assert reason == "blocked"


def test_learning_allows_once_then_suppresses():
    config = default_config()
    config["filters"]["allow"] = []
    config["filters"]["block"] = []
    config["learning"]["enabled"] = True
    config["learning"]["pending"] = {}
    config["learning"]["shown_session"] = {}

    allow1, reason1, changed1 = _evaluate_notification("app", "App", config)
    allow2, reason2, changed2 = _evaluate_notification("app", "App", config)

    assert allow1 is True
    assert reason1 == "learning_allow"
    assert changed1 is True
    assert allow2 is False
    assert reason2 == "learning_suppress"
    assert changed2 is False


def test_allow_list_blocks_unknown_when_learning_disabled():
    config = default_config()
    config["filters"]["allow"] = ["app"]
    config["filters"]["block"] = []
    config["learning"]["enabled"] = False

    allow, reason, _ = _evaluate_notification("other", "Other", config)
    assert allow is False
    assert reason == "not_in_allow"


def test_build_display_prefers_display_name():
    title, content = _build_display("Title", ["Title", "Body"], "Display", "app")
    assert title == "Display"
    assert content == "Title\nBody"


def test_build_display_falls_back_to_app_key():
    title, content = _build_display("", ["OnlyTitle"], "", "app.key")
    assert title == "app.key"
    assert content == ""


def test_notification_key_uses_id():
    class Dummy:
        id = 42

    assert _notification_key(Dummy(), "app") == "app:42"


def test_notification_key_uses_creation_time():
    class Dummy:
        id = None
        creation_time = datetime(2024, 1, 1, 0, 0, 0)

    assert _notification_key(Dummy(), "app").startswith("app:2024-01-01")


def test_prune_seen_removes_old_and_trims():
    now = datetime.now().timestamp()
    seen = {
        "old": now - 100,
        "newer": now - 1,
        "newest": now - 0.5,
    }
    _prune_seen(seen, max_age_seconds=2, max_size=1)
    assert "old" not in seen
    assert len(seen) == 1


def test_build_notification_payload_and_message():
    payload = _build_notification_payload("Title", "Body", 2.5, 0.6)
    assert payload["timeout"] == 2.5
    assert payload["opacity"] == 0.6
    message = _build_ws_message(payload)
    assert message["command"] == "SendNotification"
    assert "jsonData" in message
