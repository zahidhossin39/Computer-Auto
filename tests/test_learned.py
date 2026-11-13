"""Unit tests for src/learned.py and CommandRouter learned-command integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import pytest

from src import history, learned
from src.config import load_intents
from src.router.router import CommandRouter


@pytest.fixture(autouse=True)
def isolated_stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate learned_commands.json and history.jsonl per test."""
    learned_file = tmp_path / "learned_commands.json"
    hist_file = tmp_path / "history.jsonl"
    monkeypatch.setenv("COMPUTER_AUTO_LEARNED_PATH", str(learned_file))
    monkeypatch.setenv("COMPUTER_AUTO_HISTORY_PATH", str(hist_file))
    monkeypatch.setattr(learned, "LEARNED_PATH", learned_file)
    monkeypatch.setattr(history, "HISTORY_PATH", hist_file)
    yield learned_file, hist_file


def test_crud_and_to_intent():
    """Verify add, list, update, delete, and conversion to router Intent."""
    cmd = learned.add_command(
        name="Open Dev Dashboard",
        description="Open localhost dev server in browser",
        triggers=["open dev dashboard", "launch dev dashboard"],
        steps=[
            {"type": "open_url", "target": "https://localhost:3000"},
            {"type": "wait", "command": "300"},
            {"type": "click_element", "target": "Sign In", "automation_id": "btn_signin"},
        ],
        source_event_ids=["evt_1", "evt_2"],
    )
    assert cmd["id"].startswith("cmd_")
    assert cmd["name"] == "open_dev_dashboard"
    assert cmd["enabled"] is True
    assert cmd["uses"] == 0
    assert len(cmd["steps"]) == 3

    all_cmds = learned.list_commands()
    assert len(all_cmds) == 1

    intent = learned.to_intent(cmd)
    assert intent.name == "open_dev_dashboard"
    assert intent.category == "learned"
    assert intent.action.type == "open_url"
    assert intent.action.target == "https://localhost:3000"
    assert len(getattr(intent, "steps", [])) == 3

    updated = learned.update_command(
        cmd["id"],
        description="Updated description",
        triggers=["open dev dashboard", "start dev dashboard"],
        enabled=False,
    )
    assert updated["description"] == "Updated description"
    assert updated["enabled"] is False
    assert learned.list_commands(include_disabled=False) == []

    assert learned.delete_command(cmd["id"]) is True
    assert learned.list_commands() == []


def test_strict_step_validation_rejects_unsafe_or_unknown_steps():
    """Reject unknown types, shell/interpreter execution, and raw pixel coordinates."""
    # Unknown step type
    with pytest.raises(ValueError, match="Unsupported or forbidden"):
        learned.add_command(
            name="bad_type",
            description="bad",
            triggers=["bad"],
            steps=[{"type": "run_shell", "command": "dir"}],
        )

    # Shell executable in launch_app
    for bad_exe in ("cmd.exe", "powershell.exe", "pwsh", "bash.exe", "wscript.exe"):
        with pytest.raises(ValueError, match="forbidden"):
            learned.add_command(
                name="bad_shell",
                description="bad",
                triggers=["run script"],
                steps=[{"type": "launch_app", "target": bad_exe}],
            )

    # Shell metacharacters or flags in args
    with pytest.raises(ValueError, match="Forbidden"):
        learned.add_command(
            name="bad_args",
            description="bad",
            triggers=["run flag"],
            steps=[{"type": "launch_app", "target": "notepad.exe", "args": ["/c", "calc.exe"]}],
        )

    # Non-http URL
    with pytest.raises(ValueError, match="http"):
        learned.add_command(
            name="bad_url",
            description="bad",
            triggers=["open local file"],
            steps=[{"type": "open_url", "target": "file:///C:/Windows/System32/cmd.exe"}],
        )

    # click_element with raw pixel coordinates must be rejected
    with pytest.raises(ValueError, match="raw pixel"):
        learned.add_command(
            name="bad_click",
            description="bad",
            triggers=["click pixel"],
            steps=[{"type": "click_element", "target": "Submit", "x": 500, "y": 300}],
        )

    # click_element without UIA element name must be rejected
    with pytest.raises(ValueError, match="click_element requires"):
        learned.add_command(
            name="empty_click",
            description="bad",
            triggers=["click empty"],
            steps=[{"type": "click_element"}],
        )


def test_match_exact_fuzzy_and_disabled():
    """match() supports exact, polite-prefix, containment, and fuzzy trigger matching."""
    cmd = learned.add_command(
        name="toggle_dark_theme",
        description="Toggle application dark mode",
        triggers=["switch to dark mode", "enable night theme"],
        steps=[{"type": "hotkey", "keys": ["ctrl", "shift", "d"]}],
    )

    # Exact match
    m1 = learned.match("Please switch to the dark mode!")
    assert m1 is not None and m1["id"] == cmd["id"]
    assert m1["uses"] == 1

    # Fuzzy match (slight typo / close phrasing)
    m2 = learned.match("switch to dark mod")
    assert m2 is not None and m2["id"] == cmd["id"]
    assert m2["uses"] == 2

    # Disable command -> no longer matches
    learned.update_command(cmd["id"], enabled=False)
    assert learned.match("switch to dark mode") is None


def test_router_consults_learned_tier_and_jev_options():
    """CommandRouter routes learned triggers to 'learned' tier before Jev/Vision, and exposes them to Jev."""
    learned.add_command(
        name="spotify_liked_songs",
        description="Open Spotify Liked Songs list",
        triggers=["play my liked songs", "open spotify liked songs"],
        steps=[
            {"type": "click_element", "target": "Liked Songs"},
            {"type": "hotkey", "keys": ["space"]},
        ],
    )

    router = CommandRouter(intents=load_intents(), use_jev=False)

    # Direct learned match hits 'learned' tier instead of falling back to vision
    res = router.route("please play my liked songs")
    assert res.is_vision is False
    assert res.route == "learned"
    assert res.intent is not None
    assert res.intent.name == "spotify_liked_songs"
    assert res.intent.category == "learned"

    # Paraphrase routed via Jev option
    router.use_jev = True
    captured_options = {}

    def _fake_choose(utterance_obj, prompt, options):
        captured_options.update(options)
        for k in options:
            if k.startswith("learned:"):
                return (k, 0.95)
        return None

    with patch("src.jev.choose", side_effect=_fake_choose):
        jev_res = router.route("put on my favorite tracks in spotify")
        assert jev_res.is_vision is False
        assert jev_res.route == "learned"
        assert jev_res.intent is not None
        assert jev_res.intent.name == "spotify_liked_songs"
        assert any(k.startswith("learned:") for k in captured_options)


def test_suggest_from_history_and_approval_flow():
    """Repeated Vision tasks become disabled suggestions until approved."""
    # Record 2 successful Vision runs of the same task and 1 unrelated single run
    for _ in range(2):
        history.record_event(
            utterance="Mute Discord microphone",
            route="vision",
            intent_name=None,
            actions=[
                {"action": "click", "target": "Mute", "x": 120, "y": 880},
            ],
            success=True,
            duration_ms=2400,
        )
    history.record_event(
        utterance="one-off random vision task",
        route="vision",
        intent_name=None,
        actions=[{"action": "click", "target": "Random"}],
        success=True,
        duration_ms=1900,
    )

    events = history.read_events()
    proposals = learned.suggest_from_history(events)
    assert len(proposals) == 1
    prop = proposals[0]
    assert prop["enabled"] is False
    assert prop["suggested"] is True
    assert "mute discord microphone" in prop["triggers"]
    assert prop["steps"] == [{"type": "click_element", "target": "Mute"}]

    # Unapproved suggestion must NOT auto-run in router
    router = CommandRouter(intents=load_intents(), use_jev=False)
    before = router.route("mute discord microphone")
    assert before.is_vision is True

    # Approve suggestion -> router now routes it to 'learned'
    approved = learned.approve_suggestion(prop["id"])
    assert approved["enabled"] is True
    assert approved["suggested"] is False

    after = router.route("mute discord microphone")
    assert after.is_vision is False
    assert after.route == "learned"
    assert after.intent is not None
    assert after.intent.name == prop["name"]
