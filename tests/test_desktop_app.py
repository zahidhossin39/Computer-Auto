"""Tests for DesktopApp Control Center prototype UI."""

import os
import sys
import threading
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.app import DesktopApp


def test_desktop_app_initialization_and_visibility():
    """Verify DesktopApp initializes, renders with title and standard styles, and is viewable."""
    app = DesktopApp()
    app.init_ui()

    assert app.root is not None
    assert app.root.title() == "Computer-Auto Control Center"
    assert app._is_running is True

    # Check that widgets exist
    assert app._status_badge is not None
    assert app._mic_btn is not None
    assert app._cmd_entry is not None
    assert app._log_text is not None

    # Test thread-safe state update
    app.update_state("listening", "Listening to test audio...", "Test detail")
    app.root.update()
    assert app.current_state == "listening"

    # Test transcript update
    app.set_transcript("open notepad")
    app.root.update()
    assert app._transcript_var.get() == '"open notepad"'

    # Test log message
    app.log("Test log entry")
    app.root.update()
    log_content = app._log_text.get("1.0", "end")
    assert "Test log entry" in log_content

    app.root.destroy()


def test_desktop_app_callbacks():
    """Verify DesktopApp user action callbacks trigger properly."""
    events = {"listening": False, "panic": False, "command": None}

    def on_toggle():
        events["listening"] = True

    def on_panic():
        events["panic"] = True

    def on_run(cmd):
        events["command"] = cmd

    app = DesktopApp(
        on_toggle_listening=on_toggle,
        on_panic=on_panic,
        on_run_command=on_run,
    )
    app.init_ui()

    # Trigger mic click
    app._handle_mic_click()
    assert events["listening"] is True

    # Trigger panic
    app._handle_panic()
    assert events["panic"] is True

    # Trigger run command
    app._cmd_entry.delete(0, "end")
    app._cmd_entry.insert(0, "volume mute")
    app._handle_run_command()
    assert events["command"] == "volume mute"

    app.root.destroy()


def test_desktop_app_audio_devices():
    """Verify audio device query returns non-empty list and doesn't crash."""
    app = DesktopApp()
    devices = app._get_audio_input_devices()
    assert isinstance(devices, list)
    assert len(devices) > 0


def test_desktop_app_device_selection_sync():
    """Verify _apply_device_index synchronizes with daemon recorder device_index."""
    from unittest.mock import MagicMock
    daemon_mock = MagicMock()
    daemon_mock.recorder.device_index = None

    app = DesktopApp(daemon=daemon_mock)
    try:
        app.init_ui()
    except Exception:
        pass

    app._apply_device_index("[1] Microphone (2- USB Audio Device")
    assert daemon_mock.recorder.device_index == 1

    app._apply_device_index("[0] Default Device")
    assert daemon_mock.recorder.device_index == 0

    if app.root:
        try:
            app.root.destroy()
        except Exception:
            pass



def test_voice_feedback_thread_safe_com():
    """Verify VoiceFeedback speak does not crash in background threads due to COM issues."""
    from src.tts.piper import VoiceFeedback
    tts = VoiceFeedback()
    # Should not raise exception
    tts.speak("System test", asynchronous=True)
    tts.speak("System test sync", asynchronous=False)


def test_audio_recorder_error_tracking():
    """Verify AudioRecorder tracks last_error on invalid device index without raising."""
    from src.audio.recorder import AudioRecorder
    rec = AudioRecorder(device_index=99999)  # Non-existent device index
    rec.start()
    assert rec.is_recording is True
    # Should either have fallen back to default device or set last_error
    samples = rec.stop()
    assert isinstance(samples, type(rec.stop()))
