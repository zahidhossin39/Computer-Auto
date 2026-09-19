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
    mock_write.assert_called_once_with("hello world")


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
