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


@patch("pyautogui.write")
def test_execute_type_action(mock_write, agent):
    """Verify executing a type action inputs text."""
    action = VisionAction(action="type", text="hello world", explanation="Type query")
    success = agent.execute_action(action)

    assert success is True
    mock_write.assert_called_once_with("hello world", interval=0.01)


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
@patch("pyautogui.write")
@patch("pyautogui.click")
def test_type_into_field_clicks_then_types_then_submits(mock_click, mock_write, mock_press, agent):
    """One 'type' action can focus a field, type, and press Enter: a search in one step."""
    agent.execute_action(VisionAction(action="type", x=50, y=60, text="linkedin", submit=True))
    mock_click.assert_called_once_with(50, 60)
    mock_write.assert_called_once_with("linkedin", interval=0.01)
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
