"""Tests for Tier 2 Vision Agent."""

from unittest.mock import Mock, patch
from PIL import Image
import pytest
from src.vision.agent import VisionAgent, VisionAction


@pytest.fixture
def agent():
    return VisionAgent(api_key="fake-test-key", mock_mode=True)


def test_mock_vision_action_generation(agent):
    """Verify mock mode returns a structured VisionAction."""
    dummy_img = Image.new("RGB", (1920, 1080), color="white")
    action = agent.plan_action("click the search box", screenshot=dummy_img)

    assert isinstance(action, VisionAction)
    assert action.action in ["click", "type", "hotkey", "none"]


@patch("pyautogui.click")
def test_execute_click_action(mock_click, agent):
    """Verify executing a click action calls pyautogui with correct coordinates."""
    action = VisionAction(action="click", x=500, y=300, explanation="Click search")
    success = agent.execute_action(action)

    assert success is True
    mock_click.assert_called_once_with(500, 300)


@patch("src.vision.agent.type_text")
def test_execute_type_action(mock_type, agent):
    """Verify executing a type action inputs text."""
    action = VisionAction(action="type", text="hello world", explanation="Type query")
    success = agent.execute_action(action)

    assert success is True
    mock_type.assert_called_once_with("hello world")


def test_destructive_vision_action_is_intercepted(agent):
    """Verify that dangerous vision commands trigger guardrail requirement."""
    assert agent.guardrail.requires_confirmation("delete my files") is True


def test_marked_element_click_uses_exact_rect():
    """Planner answers with a marked element number; the click lands on that element's rect center."""
    from src.vision.uia import Element
    agent = VisionAgent(api_key="k")
    elements = [Element("A", "Button", (0, 0, 10, 10)), Element("B", "Button", (100, 100, 120, 140))]
    img = Image.new("RGB", (400, 300))
    with patch("src.vision.uia.list_elements", return_value=elements), \
         patch("src.jev.choose", return_value=("none", 1.0)), \
         patch.object(agent, "_ask", return_value={"action": "click", "element": 2, "explanation": "B"}):
        a = agent.plan_action("click B", img)
    assert (a.x, a.y) == (110, 120)

    with patch("src.vision.uia.list_elements", return_value=elements), \
         patch("src.jev.choose", return_value=("1", 0.95)):
        a = agent.plan_action("click A", img)  # confident Jev pick: no vision call needed
    assert (a.x, a.y) == (5, 5)


@patch("pyautogui.hotkey")
@patch("src.vision.agent.type_text")
@patch("pyautogui.click")
def test_type_into_field_clicks_then_types_then_submits(mock_click, mock_write, mock_press, agent):
    """One 'type' action can focus a field, type, and press Enter: a search in one step."""
    agent.execute_action(VisionAction(action="type", x=50, y=60, text="linkedin", submit=True))
    mock_click.assert_called_once_with(50, 60)
    mock_write.assert_called_once_with("linkedin")
    mock_press.assert_called_once_with("enter")  # via send_hotkey, so the poller ignores it


def test_type_without_a_target_lands_in_the_text_area():
    """A 'type' action with no element must still land somewhere real, not wherever focus is."""
    from src.vision.uia import Element
    agent = VisionAgent(api_key="k")
    elements = [Element("Close", "Button", (0, 0, 10, 10)), Element("Text editor", "Document", (0, 100, 500, 400))]
    with patch("src.vision.uia.list_elements", return_value=elements), \
         patch("src.jev.choose", return_value=("none", 1.0)), \
         patch.object(agent, "_ask", return_value={"action": "type", "text": "banana", "explanation": "type"}):
        a = agent.plan_action("type banana", Image.new("RGB", (600, 500)))
    assert (a.x, a.y) == (250, 250)


def test_mouse_actions_beyond_click(monkeypatch):
    """Scroll, double-click and right-click reach pyautogui at the element's point."""
    from unittest.mock import MagicMock
    from src.vision import agent
    from src.vision.agent import VisionAction, VisionAgent
    fake = MagicMock()
    monkeypatch.setattr(agent, "pyautogui", fake)
    v = VisionAgent(api_key="x")
    assert v.execute_action(VisionAction("scroll", 10, 20, direction="down"))
    fake.moveTo.assert_called_with(10, 20)
    fake.scroll.assert_called_with(-600)
    assert v.execute_action(VisionAction("double_click", 1, 2))
    fake.doubleClick.assert_called_with(1, 2)
    assert v.execute_action(VisionAction("right_click", 3, 4))
    fake.rightClick.assert_called_with(3, 4)


def test_json_reply_with_echoed_schema_still_parses():
    """A greedy regex glued the echoed schema and the answer into invalid JSON: the task died."""
    from src.vision.agent import _parse_json
    reply = 'Schema {"action": "click"|"type"} so: {"action": "hotkey", "keys": ["ctrl", "s"]}'
    assert _parse_json(reply) == {"action": "hotkey", "keys": ["ctrl", "s"]}


def test_multimonitor_capture_selects_secondary_with_negative_origin(monkeypatch):
    """grab_screen(hwnd) selects the monitor containing hwnd and tracks negative origin."""
    import sys
    import types
    from unittest.mock import MagicMock
    from src.vision.capture import ScreenCapture

    monitors = [
        {"left": -1920, "top": 0, "width": 3840, "height": 1080},  # virtual
        {"left": 0, "top": 0, "width": 1920, "height": 1080},      # primary
        {"left": -1920, "top": 0, "width": 1920, "height": 1080},  # left secondary
    ]

    class FakeSctImg:
        def __init__(self, w, h):
            self.size = (w, h)
            self.bgra = b"\x00" * (w * h * 4)

    class FakeMss:
        def __init__(self):
            self.monitors = monitors
            self.grabbed = None

        def grab(self, mon):
            self.grabbed = mon
            return FakeSctImg(mon["width"], mon["height"])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    fake_mss = FakeMss()
    monkeypatch.setattr("src.vision.capture.mss.mss", lambda: fake_mss)
    fake_win32 = types.SimpleNamespace(GetWindowRect=lambda hwnd: (-1800, 100, -200, 900))
    monkeypatch.setitem(sys.modules, "win32gui", fake_win32)

    cap = ScreenCapture()
    img, w, h = cap.grab_screen(hwnd=12345)
    assert (w, h) == (1920, 1080)
    assert cap.last_origin == (-1920, 0)
    assert fake_mss.grabbed == monitors[2]

    img2, ox, oy = cap.grab_for_window(12345)
    assert (ox, oy) == (-1920, 0)
    assert img2.size == (1920, 1080)


def test_multimonitor_capture_spanning_window_uses_virtual_screen(monkeypatch):
    """A window spanning two monitors captures sct.monitors[0] (the virtual desktop)."""
    import sys
    import types
    from src.vision.capture import ScreenCapture

    monitors = [
        {"left": -1920, "top": 0, "width": 3840, "height": 1080},
        {"left": 0, "top": 0, "width": 1920, "height": 1080},
        {"left": -1920, "top": 0, "width": 1920, "height": 1080},
    ]

    class FakeSctImg:
        def __init__(self, w, h):
            self.size = (w, h)
            self.bgra = b"\x00" * (w * h * 4)

    class FakeMss:
        def __init__(self):
            self.monitors = monitors

        def grab(self, mon):
            return FakeSctImg(mon["width"], mon["height"])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("src.vision.capture.mss.mss", lambda: FakeMss())
    fake_win32 = types.SimpleNamespace(GetWindowRect=lambda hwnd: (-500, 100, 500, 900))
    monkeypatch.setitem(sys.modules, "win32gui", fake_win32)

    cap = ScreenCapture()
    img, w, h = cap.grab_screen(hwnd=99)
    assert (w, h) == (3840, 1080)
    assert cap.last_origin == (-1920, 0)


def test_multimonitor_offset_mapping_for_locate_and_window_box(monkeypatch):
    """_window_box, _inside, _draw_marks, and _locate map negative-origin crops to global coords."""
    import sys
    import types
    from src.vision.agent import _draw_marks, _inside, _window_box
    from src.vision.uia import Element

    # Secondary monitor at (-1920, -200), size 1920x1080.
    # Window at global (-1720, -100) to (-720, 700) -> local (200, 100) to (1200, 900).
    fake_win32 = types.SimpleNamespace(GetWindowRect=lambda hwnd: (-1720, -100, -720, 700))
    monkeypatch.setitem(sys.modules, "win32gui", fake_win32)

    origin = (-1920, -200)
    box = _window_box(42, (1920, 1080), origin=origin)
    assert box == (200, 100, 1200, 900)

    inside_el = Element("Save", "Button", (-1600, 0, -1550, 30))
    outside_el = Element("Other", "Button", (100, 100, 150, 130))
    assert _inside(inside_el.rect, box, origin=origin) is True
    assert _inside(outside_el.rect, box, origin=origin) is False

    # Draw marks on tiny adjacent elements should succeed cleanly without overlapping tags.
    tiny = [
        Element("I1", "Button", (-1700, -80, -1684, -64)),
        Element("I2", "Button", (-1684, -80, -1668, -64)),
    ]
    marked = _draw_marks(Image.new("RGB", (1000, 800)), tiny, box, origin=origin)
    assert marked.size == (1000, 800)

    # plan_action with target grounding maps crop-relative coords back to global virtual desktop.
    agent = VisionAgent(api_key="k")
    img = Image.new("RGB", (1920, 1080))
    with patch("src.vision.uia.list_elements", return_value=[]), \
         patch.object(agent, "_ask", side_effect=[
             {"action": "click", "target": "search icon", "explanation": "click"},
             {"x": 500, "y": 500},
         ]):
        action = agent.plan_action("click search", img, hwnd=42, origin=origin)
    # crop size is (1000, 800), 500/1000 -> (500, 400) + box(200, 100) + origin(-1920, -200)
    assert (action.x, action.y) == (-1220, 300)


def test_keyless_local_endpoint_does_not_force_mock_mode(monkeypatch):
    """Blank api_key only forces mock_mode for OpenRouter; local endpoints work without Authorization."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    local = VisionAgent(api_key="", api_base="http://localhost:1234/v1")
    assert local.mock_mode is False

    explicit_mock = VisionAgent(api_key="", api_base="http://localhost:1234/v1", mock_mode=True)
    assert explicit_mock.mock_mode is True

    openrouter = VisionAgent(api_key="", api_base="https://openrouter.ai/api/v1")
    assert openrouter.mock_mode is True

    fake_resp = Mock(status_code=200)
    fake_resp.json.return_value = {"choices": [{"message": {"content": '{"action": "done"}'}}]}
    with patch("src.vision.agent._session.post", return_value=fake_resp) as mock_post:
        res = local._ask("data:image/jpeg;base64,abc", "hello")
    assert res == {"action": "done"}
    assert "Authorization" not in mock_post.call_args.kwargs["headers"]


def test_locate_clamps_and_validates_coordinates():
    """_locate validates numeric x/y and clamps to 0..1000 before scaling."""
    agent = VisionAgent(api_key="k")
    with patch.object(agent, "_ask", return_value={"x": -100, "y": 1500}):
        assert agent._locate("btn", "url", (800, 600)) == (0, 600)

    for bad in ({"x": "100", "y": 200}, {"x": True, "y": 200}, {"x": None, "y": 200}, {"x": float("nan"), "y": 200}):
        with patch.object(agent, "_ask", return_value=bad):
            with pytest.raises(ValueError):
                agent._locate("btn", "url", (800, 600))


def test_cancel_event_aborts_retry_backoff_immediately():
    """cancel_event aborts 429/503 retry backoff without stalling for seconds."""
    import threading
    import time

    agent = VisionAgent(api_key="", api_base="http://localhost:1234/v1")
    cancel = threading.Event()
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        cancel.set()
        resp = Mock(status_code=429, text="rate limited", headers={"retry-after": "8"})
        return resp

    t0 = time.monotonic()
    with patch("src.vision.agent._session.post", side_effect=fake_post):
        with pytest.raises(RuntimeError, match="cancelled"):
            agent._ask("url", "prompt", cancel_event=cancel)
    elapsed = time.monotonic() - t0
    assert calls == 1
    assert elapsed < 1.0

    # Pre-cancelled plan_action returns immediately without calling _ask.
    with patch.object(agent, "_ask") as mock_ask:
        act = agent.plan_action("click ok", Image.new("RGB", (200, 200)), cancel_event=cancel)
    assert act.action == "none"
    mock_ask.assert_not_called()


def test_locate_parses_real_ask_json_object_and_list():
    """_locate works end-to-end through _ask for both {x,y} and [{x,y}] grounding replies."""
    agent = VisionAgent(api_key="k")
    r_obj = Mock(status_code=200)
    r_obj.json.return_value = {"choices": [{"message": {"content": '{"x": 500, "y": 250}'}}]}
    with patch("src.vision.agent._session.post", return_value=r_obj):
        assert agent._locate("btn", "url", (1000, 800)) == (500, 200)

    r_list = Mock(status_code=200)
    r_list.json.return_value = {
        "choices": [{"message": {"content": '```json\n[{"x": 250, "y": 500}, {"x": 400, "y": 500}]\n```'}}]
    }
    with patch("src.vision.agent._session.post", return_value=r_list):
        assert agent._locate("btn", "url", (1000, 800)) == (250, 400)


def test_malformed_json_retries_and_succeeds():
    """If the model replies with malformed JSON once, _ask retries with repair prompt."""
    agent = VisionAgent(api_key="k")
    bad = Mock(status_code=200)
    bad.json.return_value = {"choices": [{"message": {"content": "Sure, I will click it."}}]}
    good = Mock(status_code=200)
    good.json.return_value = {
        "choices": [{"message": {"content": [{"type": "text", "text": '{"action": "done", "explanation": "ok"}'}]}}]
    }
    with patch("src.vision.agent._session.post", side_effect=[bad, good]) as mock_post:
        res = agent._ask("url", "prompt")
    assert res["action"] == "done"
    assert mock_post.call_count == 2


def test_string_element_index_and_reasoning_model_payload():
    """String digit element indices resolve cleanly and reasoning models omit temperature=0."""
    from src.vision.uia import Element
    agent = VisionAgent(api_key="k", model_name="openai/gpt-5")
    elements = [Element("A", "Button", (0, 0, 20, 20)), Element("B", "Button", (40, 40, 80, 80))]
    good = Mock(status_code=200)
    good.json.return_value = {
        "choices": [{"message": {"content": '{"action": "click", "element": "2", "explanation": "click B"}'}}]
    }
    with patch("src.vision.uia.list_elements", return_value=elements), \
         patch("src.jev.choose", return_value=("none", 1.0)), \
         patch("src.vision.agent._session.post", return_value=good) as mock_post:
        act = agent.plan_action("click B", Image.new("RGB", (200, 200)))
    assert (act.x, act.y) == (60, 60)
    assert "temperature" not in mock_post.call_args.kwargs["json"]


def test_api_key_and_quota_errors_surfaced_clearly(monkeypatch):
    """HTTP 401/402 and missing OpenRouter key surface clear messages to the UI."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    missing = VisionAgent(api_key="", api_base="https://openrouter.ai/api/v1")
    act_missing = missing.plan_action("click ok", Image.new("RGB", (200, 200)))
    assert act_missing.action == "none"
    assert "API key missing" in act_missing.explanation

    agent = VisionAgent(api_key="bad-key")
    resp_401 = Mock(status_code=401, text='{"error":{"message":"User not found"}}', headers={})
    with patch("src.vision.uia.list_elements", return_value=[]), \
         patch("src.vision.agent._session.post", return_value=resp_401):
        act_401 = agent.plan_action("click ok", Image.new("RGB", (200, 200)))
    assert act_401.action == "none"
    assert "Invalid API key" in act_401.explanation

    resp_402 = Mock(status_code=402, text='{"error":{"message":"Insufficient credits"}}', headers={})
    with patch("src.vision.uia.list_elements", return_value=[]), \
         patch("src.vision.agent._session.post", return_value=resp_402):
        act_402 = agent.plan_action("click ok", Image.new("RGB", (200, 200)))
    assert act_402.action == "none"
    assert "quota or credits exceeded" in act_402.explanation
