"""Unit tests for src/history.py (append-only JSONL history log)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading
from pathlib import Path
import pytest

from src import history


@pytest.fixture(autouse=True)
def isolated_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect history.jsonl to a temporary directory for every test."""
    hist_file = tmp_path / "history.jsonl"
    monkeypatch.setenv("COMPUTER_AUTO_HISTORY_PATH", str(hist_file))
    monkeypatch.setattr(history, "HISTORY_PATH", hist_file)
    monkeypatch.setattr(history, "MAX_HISTORY_BYTES", 2 * 1024 * 1024)
    yield hist_file


def test_record_and_read_events(isolated_history: Path):
    """Recorded events include id, ISO ts, route, actions, success, duration_ms, error."""
    history.record_event(
        utterance="volume up",
        route="keyword",
        intent_name="volume_up",
        actions=[{"type": "system_action", "command": "volume_step_up"}],
        success=True,
        duration_ms=12,
    )
    history.record_event(
        utterance="click the green submit button",
        route="vision",
        intent_name=None,
        actions=[{"action": "click", "target": "Submit", "x": 400, "y": 300}],
        success=False,
        duration_ms=3450,
        error="Element disappeared",
    )

    events = history.read_events()
    assert len(events) == 2

    ev1, ev2 = events[0], events[1]
    assert ev1["id"].startswith("evt_")
    assert "T" in ev1["ts"]
    assert ev1["utterance"] == "volume up"
    assert ev1["route"] == "keyword"
    assert ev1["intent_name"] == "volume_up"
    assert ev1["success"] is True
    assert ev1["duration_ms"] == 12
    assert ev1["error"] is None

    assert ev2["utterance"] == "click the green submit button"
    assert ev2["route"] == "vision"
    assert ev2["intent_name"] is None
    assert ev2["success"] is False
    assert ev2["duration_ms"] == 3450
    assert ev2["error"] == "Element disappeared"


def test_read_events_filters_limit_route_and_since():
    """read_events filters by route, ISO since timestamp, and limit."""
    t0 = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    history.record_event("open notepad", "keyword", "launch_notepad", [], True, 15)
    t_mid = datetime.now(timezone.utc).isoformat()
    history.record_event("open spotify playlist", "vision", None, [{"action": "click", "target": "Liked Songs"}], True, 1800)
    history.record_event("type hello", "slot", "type_text", [{"type": "type_text", "target": "hello"}], True, 25)

    vision_only = history.read_events(route="vision")
    assert len(vision_only) == 1
    assert vision_only[0]["utterance"] == "open spotify playlist"

    since_mid = history.read_events(since=t_mid)
    assert len(since_mid) == 2
    assert [e["route"] for e in since_mid] == ["vision", "slot"]

    since_all = history.read_events(since=t0, limit=1)
    assert len(since_all) == 1
    assert since_all[0]["utterance"] == "type hello"

    assert history.read_events(limit=0) == []


def test_thread_safe_concurrent_appends():
    """Concurrent threads appending events produce valid, uncorrupted JSONL lines."""
    threads = []
    for t_idx in range(6):
        def _worker(idx=t_idx):
            for i in range(15):
                history.record_event(
                    utterance=f"cmd-{idx}-{i}",
                    route="vision" if i % 2 == 0 else "keyword",
                    intent_name=None,
                    actions=[{"action": "hotkey", "keys": ["ctrl", "t"]}],
                    success=True,
                    duration_ms=50 + i,
                )
        t = threading.Thread(target=_worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    events = history.read_events(limit=500)
    assert len(events) == 90


def test_rotation_caps_file_size(isolated_history: Path, monkeypatch: pytest.MonkeyPatch):
    """When history.jsonl exceeds MAX_HISTORY_BYTES, older records are rotated out."""
    monkeypatch.setattr(history, "MAX_HISTORY_BYTES", 1200)
    for i in range(25):
        history.record_event(
            utterance=f"repeated vision command number {i}",
            route="vision",
            intent_name=None,
            actions=[{"action": "click", "target": f"Button {i}"}],
            success=True,
            duration_ms=100,
        )

    assert isolated_history.stat().st_size <= 1200
    events = history.read_events(limit=100)
    assert 1 <= len(events) < 25
    assert events[-1]["utterance"] == "repeated vision command number 24"


def test_record_event_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """record_event never raises even if target path is a directory or inputs are malformed."""
    bad_path = tmp_path / "is_a_dir"
    bad_path.mkdir()
    # Passing a directory path or non-serializable objects must not raise
    history.record_event(
        utterance="test",
        route="unknown_route_value",
        intent_name=None,
        actions=[{"bad": object()}],  # type: ignore[dict-item]
        success=True,
        duration_ms="not-an-int",  # type: ignore[arg-type]
        path=bad_path,
    )
