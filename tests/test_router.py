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


def test_long_sentence_containing_trigger_routes_to_vision(router):
    """Verify a trigger buried in a long sentence falls through to vision."""
    res = router.route("choose an account from open browser and")
    assert res.is_vision is True
    assert res.intent is None


def test_short_command_with_extra_words_still_matches(router):
    """Verify short utterances with extra words around a trigger still route."""
    res = router.route("please open notepad")
    assert res.is_vision is False
    assert res.intent is not None
    assert res.intent.name == "launch_notepad"


def test_articles_are_ignored(router):
    """'open the browser' matches the 'open browser' trigger."""
    res = router.route("open the browser")
    assert res.intent is not None and res.intent.name == "launch_browser"


def test_jev_routes_paraphrase_and_low_confidence_goes_to_vision(router):
    """Jev maps paraphrases to intents; unsure answers fall through to vision."""
    from unittest.mock import patch
    router.use_jev = True
    with patch("src.jev.choose", return_value=("launch_notepad", 0.97)):
        assert router.route("fire up the text editor").intent.name == "launch_notepad"
    with patch("src.jev.choose", return_value=("launch_notepad", 0.5)):
        assert router.route("fire up the text editor").is_vision is True
    with patch("src.jev.choose", return_value=None):  # Jev down -> vision, never crash
        assert router.route("fire up the text editor").is_vision is True


def test_argument_commands_skip_vision(router):
    """type/go to/google are deterministic; no model call needed."""
    assert router.route("type hello world").intent.action.target == "hello world"
    assert router.route("go to youtube.com").intent.action.target == "https://youtube.com"
    assert "q=best+pizza" in router.route("google best pizza").intent.action.target
    assert router.route("open new tab").intent.action.keys == ["ctrl", "t"]
