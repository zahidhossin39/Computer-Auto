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

    r_upset = router.route("okay close this upset")
    assert r_upset.is_vision is False
    assert r_upset.intent.name == "close_tab"

    r_chrome_open = router.route("open chrome browser that is already open on the")
    assert r_chrome_open.is_vision is False
    assert r_chrome_open.intent.name == "focus_window"
    assert r_chrome_open.intent.action.target == "456"


def test_chrome_multi_profile_and_gmail_routing(router, monkeypatch):
    """Verify ordinal and named Chrome profiles / Gmail accounts route deterministically."""
    from src import apps

    sample_profiles = [
        {"index": 1, "dir": "Default", "name": "Zaid hossain", "email": "zahidhossin39@gmail.com"},
        {"index": 2, "dir": "Profile 2", "name": "Zaid", "email": "zahidhossin509@gmail.com"},
        {"index": 3, "dir": "Profile 5", "name": "Zaid", "email": "zahidhosson28@gmail.com"},
        {"index": 4, "dir": "Profile 6", "name": "zahid", "email": "zahidhossain3009@gmail.com"},
        {"index": 5, "dir": "Profile 7", "name": "Zaid", "email": "hello.zaidhossain@gmail.com"},
        {"index": 6, "dir": "Profile 8", "name": "Zaid.W", "email": "work.zaid.business@gmail.com"},
    ]
    monkeypatch.setattr(apps, "chrome_profiles", lambda: sample_profiles)

    for phrase in (
        "open 3rd gmail",
        "open third number gmail",
        "open 3 third number gmail",
        "open gmail 3",
        "go to 3rd email",
    ):
        res = router.route(phrase)
        assert res.is_vision is False, f"Failed on {phrase!r}"
        assert res.intent.name == "open_chrome_gmail"
        assert res.intent.action.type == "launch_app"
        assert res.intent.action.target == "chrome.exe"
        assert res.intent.action.args == ["--profile-directory=Profile 5", "https://mail.google.com"]

    for phrase in (
        "open third number profile",
        "open 3rd profile in chrome",
        "open chrome 3rd profile",
        "switch to profile 3",
    ):
        res = router.route(phrase)
        assert res.is_vision is False, f"Failed on {phrase!r}"
        assert res.intent.name == "open_chrome_profile"
        assert res.intent.action.args == ["--profile-directory=Profile 5"]

    res_5 = router.route("open 5th gmail")
    assert res_5.is_vision is False
    assert res_5.intent.action.args == ["--profile-directory=Profile 7", "https://mail.google.com"]

    res_6 = router.route("open 6th gmail")
    assert res_6.is_vision is False
    assert res_6.intent.action.args == ["--profile-directory=Profile 8", "https://mail.google.com"]

    res_work = router.route("open work gmail")
    assert res_work.is_vision is False
    assert res_work.intent.action.args == ["--profile-directory=Profile 8", "https://mail.google.com"]

    res_last = router.route("open last chrome profile")
    assert res_last.is_vision is False
    assert res_last.intent.action.args == ["--profile-directory=Profile 8"]

    # Out-of-bounds profile ordinal should not match a nonexistent profile
    res_oob = router.route("open 9th gmail")
    assert res_oob.intent is None or res_oob.intent.name != "open_chrome_gmail"


def test_jev_decision_model_turns_decisions_into_commands(router, monkeypatch):
    """Verify Jev decision model converts dynamic Chrome profile, window, site, and app choices into commands."""
    from unittest.mock import patch
    from src import apps

    sample_profiles = [
        {"index": 1, "dir": "Default", "name": "Zaid hossain", "email": "zahidhossin39@gmail.com"},
        {"index": 2, "dir": "Profile 2", "name": "Zaid", "email": "zahidhossin509@gmail.com"},
        {"index": 3, "dir": "Profile 5", "name": "Zaid", "email": "zahidhosson28@gmail.com"},
    ]
    monkeypatch.setattr(apps, "chrome_profiles", lambda: sample_profiles)
    monkeypatch.setattr(apps, "open_windows", lambda: [(321, "Google Chrome"), (654, "Discord")])
    router.use_jev = True

    with patch("src.jev.choose", return_value=("chrome_gmail:Profile 5", 0.94)):
        res = router.route("check the inbox on my third account please")
        assert res.is_vision is False
        assert res.intent.name == "open_chrome_gmail"
        assert res.intent.action.args == ["--profile-directory=Profile 5", "https://mail.google.com"]

    with patch("src.jev.choose", return_value=("chrome_profile:Profile 2", 0.91)):
        res = router.route("let me use my second browser persona")
        assert res.is_vision is False
        assert res.intent.name == "open_chrome_profile"
        assert res.intent.action.args == ["--profile-directory=Profile 2"]

    with patch("src.jev.choose", return_value=("focus_win:321:Google Chrome", 0.92)):
        res = router.route("return my attention to the web session")
        assert res.is_vision is False
        assert res.intent.name == "focus_window"
        assert res.intent.action.target == "321"

    with patch("src.jev.choose", return_value=("min_win:654:Discord", 0.90)):
        res = router.route("put the chat window away for now")
        assert res.is_vision is False
        assert res.intent.name == "minimize_window"
        assert res.intent.action.target == "654"

    with patch("src.jev.choose", return_value=("site:gmail", 0.95)):
        res = router.route("take me to my email")
        assert res.is_vision is False
        assert res.intent.action.type == "open_url"
        assert res.intent.action.target == "https://mail.google.com"


def test_chrome_local_state_parsing_and_profile_lookup(tmp_path):
    """Verify apps.chrome_profiles and apps.find_chrome_profile parse Chrome's Local State JSON."""
    import json
    from src import apps

    local_state = {
        "profile": {
            "profiles_order": ["Default", "Profile 2", "Profile 5", "Profile 8"],
            "info_cache": {
                "Default": {"name": "Zaid hossain", "user_name": "zahidhossin39@gmail.com"},
                "Profile 2": {"name": "Zaid", "user_name": "zahidhossin509@gmail.com"},
                "Profile 5": {"name": "Zaid", "user_name": "zahidhosson28@gmail.com"},
                "Profile 8": {"name": "Zaid.W", "user_name": "work.zaid.business@gmail.com"},
            },
        }
    }
    state_file = tmp_path / "Local State"
    state_file.write_text(json.dumps(local_state), encoding="utf-8")

    profs = apps.chrome_profiles(local_state_path=str(state_file))
    assert len(profs) == 4
    assert profs[2]["dir"] == "Profile 5"
    assert profs[2]["index"] == 3

    p3 = apps.find_chrome_profile("third number", local_state_path=str(state_file))
    assert p3 is not None and p3["dir"] == "Profile 5"

    p_work = apps.find_chrome_profile("work", local_state_path=str(state_file))
    assert p_work is not None and p_work["dir"] == "Profile 8"

    p_last = apps.find_chrome_profile("last", local_state_path=str(state_file))
    assert p_last is not None and p_last["dir"] == "Profile 8"

    assert apps.find_chrome_profile("9th", local_state_path=str(state_file)) is None


def test_open_chrome_window_does_not_hijack_browser_tab_history_or_compound_commands(router, monkeypatch):
    """Regression test: when Chrome is open, 'close the browser tab', 'open browser history',
    'open new browser tab', 'open firefox browser', and 'open browser and type hello' must NOT
    be hijacked by apps.find_window('browser') as close_window or focus_window."""
    from src import apps

    monkeypatch.setattr(
        apps,
        "open_windows",
        lambda: [(983670, "New Tab - Google Chrome", "chrome.exe")],
    )
    monkeypatch.setattr(apps, "find", lambda name: None)

    r_close_tab = router.route("close the browser tab")
    assert r_close_tab.is_vision is False
    assert r_close_tab.intent.name == "close_tab"
    assert r_close_tab.intent.action.type == "hotkey"

    r_history = router.route("open browser history")
    assert r_history.is_vision is False
    assert r_history.intent.name == "show_history"

    r_new_tab = router.route("open new browser tab")
    assert r_new_tab.is_vision is False
    assert r_new_tab.intent.name == "new_tab"

    r_firefox = router.route("open firefox browser")
    assert r_firefox.intent is None or r_firefox.intent.name != "focus_window"

    r_compound = router.route("open browser and type hello")
    assert r_compound.is_vision is True

    # Generic 'focus browser' and 'open the browser that is already opened' focus Chrome
    r_focus1 = router.route("focus browser")
    assert r_focus1.is_vision is False
    assert r_focus1.intent.name == "focus_window"
    assert r_focus1.intent.action.target == "983670"

    r_focus2 = router.route("open the browser that is already opened")
    assert r_focus2.is_vision is False
    assert r_focus2.intent.name == "focus_window"
    assert r_focus2.intent.action.target == "983670"


def test_chrome_profile_slot_extended_phrasings_and_compound_rejection(router, monkeypatch):
    """Verify 'check 3rd gmail', 'in google chrome open third number profile', 'open my gmail',
    and rejection of compound commands like 'open notepad and type my 1st email'."""
    from src import apps

    sample_profiles = [
        {"index": 1, "dir": "Default", "name": "Zaid hossain", "email": "zahidhossin39@gmail.com"},
        {"index": 2, "dir": "Profile 2", "name": "Zaid", "email": "zahidhossin509@gmail.com"},
        {"index": 3, "dir": "Profile 5", "name": "Zaid", "email": "zahidhosson28@gmail.com"},
        {"index": 4, "dir": "Profile 6", "name": "zahid", "email": "zahidhossain3009@gmail.com"},
        {"index": 5, "dir": "Profile 7", "name": "Zaid", "email": "hello.zaidhossain@gmail.com"},
    ]
    monkeypatch.setattr(apps, "chrome_profiles", lambda: sample_profiles)

    r_check = router.route("check 3rd gmail")
    assert r_check.is_vision is False
    assert r_check.intent.name == "open_chrome_gmail"
    assert r_check.intent.action.args == ["--profile-directory=Profile 5", "https://mail.google.com"]

    r_check_5 = router.route("check my 5th email")
    assert r_check_5.is_vision is False
    assert r_check_5.intent.name == "open_chrome_gmail"
    assert r_check_5.intent.action.args == ["--profile-directory=Profile 7", "https://mail.google.com"]

    r_in_google = router.route("in google chrome open third number profile")
    assert r_in_google.is_vision is False
    assert r_in_google.intent.name == "open_chrome_profile"
    assert r_in_google.intent.action.args == ["--profile-directory=Profile 5"]

    r_my_gmail = router.route("open my gmail")
    assert r_my_gmail.is_vision is False
    assert r_my_gmail.intent.action.type == "open_url"
    assert r_my_gmail.intent.action.target == "https://mail.google.com"

    # Compound command must NOT be hijacked by _match_chrome_profile_slot
    r_compound = router.route("open notepad and type my 1st email")
    assert r_compound.is_vision is True


def test_jev_options_deduplicated_no_probability_split(router, monkeypatch):
    """Verify _jev_route does not add duplicate open_app options for apps already in static intents."""
    from unittest.mock import patch
    from src import apps

    monkeypatch.setattr(apps, "chrome_profiles", lambda: [])
    router.use_jev = True
    captured_options = {}

    def fake_choose(ctx, question, options):
        captured_options.update(options)
        return ("launch_notepad", 0.99)

    with patch("src.jev.choose", side_effect=fake_choose):
        res = router.route("fire up the text editor")
        assert res.is_vision is False
        assert res.intent.name == "launch_notepad"

    assert "launch_notepad" in captured_options
    assert "open_app:notepad" not in captured_options
    assert "open_app:calculator" not in captured_options
    assert "open_app:chrome" not in captured_options



