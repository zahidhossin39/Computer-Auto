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


def test_one_word_triggers_do_not_fire_inside_sentences(router):
    """"print my name" must not press ctrl+p; "print" alone still does."""
    assert router.route("print").intent.name == "print"
    assert router.route("print my name").is_vision
    assert router.route("cut the grass").is_vision


def test_close_an_app_that_is_not_open_does_not_close_the_front_window(router, monkeypatch):
    """Jev mapped "close spotify" to "close the active window"; it must just say so instead."""
    from src import apps
    monkeypatch.setattr(apps, "find_window", lambda name: None)
    monkeypatch.setattr(apps, "find", lambda name, allow_jev=True: ("Spotify", "Spotify.AppID") if "spotify" in name else None)
    res = router.route("close spotify")
    assert res.intent.action.type == "say"
    monkeypatch.setattr(apps, "find_window", lambda name: (123, "Spotify Premium"))
    res = router.route("switch to spotify")
    assert res.intent.action.type == "focus_window" and res.intent.action.target == "123"


def test_close_ui_targets_fall_through_to_vision(router, monkeypatch):
    """UI targets like 'close popup' or 'exit fullscreen' must fall through to Vision, not say not_open."""
    from src import apps
    monkeypatch.setattr(apps, "find_window", lambda name: None)
    monkeypatch.setattr(apps, "find", lambda name, allow_jev=True: None)
    for cmd in ("close popup", "close sidebar", "close modal", "close dialog", "close ad", "exit fullscreen"):
        res = router.route(cmd)
        assert res.is_vision is True, f"Expected {cmd!r} to fall through to Vision"
        assert res.intent is None


def test_minimize_maximize_restore_app_routing(router, monkeypatch):
    """minimize/maximize/restore <app> routes deterministically via find_window."""
    from src import apps
    monkeypatch.setattr(apps, "find_window", lambda name: (456, "Claude") if "cloud" in name or "claude" in name or "chrome" in name or "notepad" in name or "discord" in name else None)

    r_min = router.route("minimize chrome")
    assert r_min.is_vision is False
    assert r_min.intent.action.type == "minimize_window"
    assert r_min.intent.action.target == "456"

    r_typo = router.route("minimized cloud")
    assert r_typo.is_vision is False
    assert r_typo.intent.action.type == "minimize_window"
    assert r_typo.intent.action.target == "456"

    r_max = router.route("maximize notepad")
    assert r_max.is_vision is False
    assert r_max.intent.action.type == "maximize_window"
    assert r_max.intent.action.target == "456"

    r_res = router.route("restore discord")
    assert r_res.is_vision is False
    assert r_res.intent.action.type == "restore_window"
    assert r_res.intent.action.target == "456"


def test_press_any_key_combination(router):
    assert router.route("press control shift t").intent.action.keys == ["ctrl", "shift", "t"]
    assert router.route("press f5").intent.action.keys == ["f5"]
    assert router.route("press shift tab").intent.action.keys == ["shift", "tab"]
    assert router.route("press the red button").is_vision  # not keys: let vision find it


def test_sites_files_and_dictation(router, monkeypatch):
    from src import apps
    monkeypatch.setattr(apps, "find_window", lambda name: None)
    monkeypatch.setattr(apps, "find", lambda name: None)
    exe = router.route("open notepad.exe")
    assert exe.intent is None or exe.intent.action.type != "open_url"  # a file, not a website
    assert router.route("go to youtube").intent.action.target == "https://www.youtube.com"
    assert "search_query=lofi+music" in router.route("search youtube for lofi music").intent.action.target
    assert "q=cats" in router.route("search the web for cats").intent.action.target
    assert router.route("type hello comma world new line bye").intent.action.target == "hello, world\nbye"


def test_search_bar_typing_slot_intent(router):
    r1 = router.route("in the search bar, type my website")
    assert r1.is_vision is False
    assert r1.intent.name == "search_in_browser"
    assert r1.intent.action.type == "search_in_browser"
    assert r1.intent.action.target == "my website"

    r2 = router.route("type github in the address bar")
    assert r2.is_vision is False
    assert r2.intent.name == "search_in_browser"
    assert r2.intent.action.target == "github"


def test_type_in_target_window(router, monkeypatch):
    from src import apps
    monkeypatch.setattr(apps, "find_window", lambda name: (789, "Notepad - Untitled") if "notepad" in name.lower() else None)

    r1 = router.route("type in notepad hello world")
    assert r1.is_vision is False
    assert r1.intent.name == "type_in_window"
    assert r1.intent.action.type == "type_in_window"
    assert r1.intent.action.target == "hello world"
    assert r1.intent.action.args == ["789"]

    r2 = router.route("in notepad type test code")
    assert r2.is_vision is False
    assert r2.intent.name == "type_in_window"
    assert r2.intent.action.target == "test code"


def test_phonetic_and_relative_window_fixes(router, monkeypatch):
    from src import apps
    monkeypatch.setattr(apps, "find_window", lambda name: (456, "Google Chrome") if any(k in name.lower() for k in ("chrome", "browser")) else ((525580, "Discord") if "discord" in name.lower() else None))

    r_min = router.route("minima's discord")
    assert r_min.is_vision is False
    assert r_min.intent.action.type == "minimize_window"
    assert r_min.intent.action.target == "525580"

    r_focus = router.route("open the browser that is already opened")
    assert r_focus.is_vision is False
    assert r_focus.intent.name == "focus_window"
    assert r_focus.intent.action.target == "456"

    r_tab = router.route("open new debt")
    assert r_tab.is_vision is False
    assert r_tab.intent.name == "new_tab"

    r_close = router.route("close this website only")
    assert r_close.is_vision is False
    assert r_close.intent.name == "close_tab"
