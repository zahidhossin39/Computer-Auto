"""Regression tests for daemon state-machine bugs.

Covers:
- Guardrail confirmation dead-end (destructive intents could never execute)
- Double-stop race (duplicate on_listening_toggle spawning duplicate workers)
- Panic desync (UI panic not resetting hotkey detector state)
"""
import os
import sys
import time
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import ComputerAutoDaemon


def _make_daemon() -> ComputerAutoDaemon:
    """Build a daemon with hardware-touching subsystems stubbed out."""
    daemon = ComputerAutoDaemon(mock_stt=True, mock_vision=True, ui_mode="none")
    daemon.router.use_jev = False  # no network in tests
    daemon.recorder = MagicMock()
    daemon.recorder.is_recording = False
    daemon.recorder.last_error = None
    daemon.recorder.sample_rate = 16000
    daemon.recorder.stop.return_value = np.empty(0, dtype=np.float32)

    def _fake_start():
        daemon.recorder.is_recording = True

    def _fake_stop():
        daemon.recorder.is_recording = False
        return np.empty(0, dtype=np.float32)

    daemon.recorder.start.side_effect = _fake_start
    daemon.recorder.stop.side_effect = _fake_stop
    # Silence TTS and chimes during tests
    daemon.tts = MagicMock()
    daemon.play_sound = lambda *a, **k: None
    return daemon


def test_guardrail_confirmation_flow():
    """Destructive intent parks confirmation; 'yes' executes, 'no' cancels."""
    daemon = _make_daemon()
    daemon.executor = MagicMock()

    # 1. Destructive command must NOT execute immediately
    daemon.handle_command("close window")
    daemon.executor.execute_system_action.assert_not_called()
    assert daemon._pending_confirmation == "close window"

    # 2. 'no' cancels the pending action
    daemon.handle_command("no")
    daemon.executor.execute_system_action.assert_not_called()
    assert daemon._pending_confirmation is None

    # 3. Re-request, then confirm with 'yes' -> executes
    daemon.handle_command("close window")
    assert daemon._pending_confirmation == "close window"
    daemon.handle_command("yes")
    daemon.executor.execute_system_action.assert_called_once_with("window_close_active")
    assert daemon._pending_confirmation is None


def test_guardrail_new_command_supersedes_pending():
    """A different command clears the pending confirmation and runs normally."""
    daemon = _make_daemon()
    daemon.executor = MagicMock()

    daemon.handle_command("close window")
    assert daemon._pending_confirmation == "close window"

    daemon.handle_command("volume up")
    assert daemon._pending_confirmation is None
    daemon.executor.execute_system_action.assert_called_once_with("volume_step_up")


def test_listening_toggle_idempotent():
    """Duplicate toggles (VAD auto-stop racing manual stop) are ignored."""
    daemon = _make_daemon()

    # Stop while never started: no-op, recorder untouched
    daemon.on_listening_toggle(False)
    daemon.recorder.stop.assert_not_called()

    # Start once; duplicate start toggle ignored
    daemon.on_listening_toggle(True)
    daemon.on_listening_toggle(True)
    assert daemon.recorder.start.call_count == 1

    # Stop twice: only one stop worker spawned
    daemon.on_listening_toggle(False)
    daemon.on_listening_toggle(False)
    time.sleep(0.2)  # let the worker thread run
    assert daemon.recorder.stop.call_count == 1


def test_mic_start_failure_reverts_listening_state():
    """If the mic fails to open, listening state reverts so next toggle works."""
    daemon = _make_daemon()
    # Simulate a failed mic open: start() leaves is_recording False
    daemon.recorder.start.side_effect = lambda: None
    daemon.recorder.is_recording = False
    daemon.recorder.last_error = "Failed to open audio input"

    daemon.on_listening_toggle(True)
    assert daemon._listening_active is False
    assert daemon.hotkey_listener.detector.is_listening is False

    # State reverted -> a retry actually attempts to start the recorder again
    daemon.on_listening_toggle(True)
    assert daemon.recorder.start.call_count == 2


def test_panic_resets_detector_and_pending():
    """Panic from any source must resync hotkey detector and clear pending."""
    daemon = _make_daemon()
    daemon._listening_active = True
    daemon.hotkey_listener.detector.is_listening = True
    daemon.hotkey_listener.detector.last_tap_time = 123.0
    daemon._pending_confirmation = "close window"

    daemon.on_panic_key()

    assert daemon._listening_active is False
    assert daemon.hotkey_listener.detector.is_listening is False
    assert daemon.hotkey_listener.detector.last_tap_time == 0.0
    assert daemon._pending_confirmation is None


def test_continuous_mode_rearms_and_panic_ends_it():
    """Continuous mode re-arms the mic after each utterance; panic turns it off."""
    daemon = _make_daemon()
    daemon.toggle_session()
    assert daemon.recorder.is_recording

    daemon.on_listening_toggle(False)  # VAD stop -> worker runs -> should re-arm
    for _ in range(250):  # up to 5s on a loaded machine
        if daemon.recorder.is_recording:
            break
        time.sleep(0.02)
    assert daemon.recorder.is_recording and daemon._listening_active

    daemon.toggle_session()  # second double-tap ends the session
    assert daemon.continuous is False and not daemon._listening_active

    daemon.toggle_session()
    daemon.on_panic_key()
    assert daemon.continuous is False and not daemon.recorder.is_recording


def test_vision_loop_runs_until_done():
    """Vision agent keeps stepping with history until it reports done."""
    from src.vision.agent import VisionAction
    daemon = _make_daemon()
    daemon.capture = MagicMock()
    daemon.capture.grab_screen.return_value = (MagicMock(), 100, 100)
    daemon.vision = MagicMock()
    daemon.vision.plan_action.side_effect = [
        VisionAction(action="click", x=1, y=1, explanation="step one"),
        VisionAction(action="done", explanation="finished"),
    ]
    daemon.vision.execute_action.return_value = True
    daemon.handle_command("choose an account from open browser and")
    assert daemon.vision.plan_action.call_count == 2
    assert daemon.vision.plan_action.call_args[0][2] == ["click: step one"]


def test_vision_loop_stops_when_action_has_no_effect():
    """The same action three times means the screen is not responding: stop instead of looping."""
    from src.vision.agent import VisionAction
    daemon = _make_daemon()
    daemon.capture = MagicMock()
    daemon.capture.grab_screen.return_value = (MagicMock(), 100, 100)
    daemon.vision = MagicMock()
    daemon.vision.plan_action.return_value = VisionAction(action="type", text="hi", explanation="type hi")
    daemon.vision.execute_action.return_value = True
    daemon.handle_command("put hi everywhere")
    assert daemon.vision.plan_action.call_count == 2  # stops as soon as it repeats itself
    assert daemon.vision.execute_action.call_count == 1  # and never does it twice


def test_vision_loop_ends_after_final_action():
    """'open new tab' clicked New Tab, then pressed ctrl+t twice more: a final action ends the task."""
    from src.vision.agent import VisionAction
    daemon = _make_daemon()
    daemon.capture = MagicMock()
    daemon.capture.grab_screen.return_value = (MagicMock(), 100, 100)
    daemon.vision = MagicMock()
    daemon.vision.plan_action.return_value = VisionAction("click", 5, 5, final=True, explanation="New Tab")
    daemon.vision.execute_action.return_value = True
    daemon.handle_command("put a tab somewhere")
    assert daemon.vision.plan_action.call_count == 1


def test_compound_command_runs_each_known_part():
    """"open notepad and type hi" is two known intents: no vision call."""
    daemon = _make_daemon()
    daemon.vision = MagicMock()
    daemon.executor = MagicMock()
    daemon.handle_command("open notepad and type hi")
    daemon.executor.launch_app.assert_called_once()
    assert daemon.executor.run_action.call_args[0][0].target == "hi"
    daemon.vision.plan_action.assert_not_called()
