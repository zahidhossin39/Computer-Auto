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
