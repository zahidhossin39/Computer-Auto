"""Tests for Command Router."""

import pytest
from src.config import load_intents
from src.router.router import CommandRouter, RouteResult


@pytest.fixture
def router():
    intents = load_intents()
    return CommandRouter(intents)


def test_exact_trigger_routing(router):
    """Verify exact trigger match resolves to the correct system intent."""
    res = router.route("volume up")
    assert isinstance(res, RouteResult)
    assert res.is_vision is False
    assert res.intent is not None
    assert res.intent.name == "volume_up"
    assert res.intent.action.command == "volume_step_up"


def test_case_insensitive_and_punctuation_normalization(router):
    """Verify router ignores case, punctuation, and leading/trailing whitespace."""
    res = router.route("  Turn up Volume!  ")
    assert res.is_vision is False
    assert res.intent.name == "volume_up"

    res_mute = router.route("Mute.")
    assert res_mute.intent.name == "volume_mute"


def test_app_launch_routing(router):
    """Verify application launching intents."""
    res = router.route("open notepad")
    assert res.is_vision is False
    assert res.intent.name == "launch_notepad"
    assert res.intent.action.type == "launch_app"
    assert res.intent.action.target == "notepad.exe"


def test_window_management_routing(router):
    """Verify window snapping and minimize intents."""
    res_snap = router.route("snap left")
    assert res_snap.intent.name == "window_snap_left"

    res_min = router.route("minimize")
    assert res_min.intent.name == "window_minimize"


def test_unmatched_command_routes_to_vision_agent(router):
    """Verify open-ended or unscripted commands fall back to Tier 2 Vision Agent."""
    unscripted_queries = [
        "click on the green submit button",
        "scroll down and select the second link",
        "write an email to John saying I will be late",
        "order a pizza from Domino's in Chrome",
        "highlight all the text in the document and make it bold",
    ]
    for query in unscripted_queries:
        res = router.route(query)
        assert res.is_vision is True
        assert res.command == query.strip()
        assert res.intent is None
