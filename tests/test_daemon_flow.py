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


def test_mixed_chain_runs_known_part_then_vision(monkeypatch):
    """"open notepad and click the third menu item": launch instantly, vision gets only the rest."""
    from src.vision.agent import VisionAction
    monkeypatch.setattr("main.time.sleep", lambda s: None)
    daemon = _make_daemon()
    daemon.executor = MagicMock()
    daemon.capture = MagicMock()
    daemon.capture.grab_screen.return_value = (MagicMock(), 100, 100)
    daemon.vision = MagicMock()
    daemon.vision.plan_action.return_value = VisionAction(action="done", explanation="ok")
    daemon.handle_command("open notepad and click the third menu item")
    daemon.executor.launch_app.assert_called_once()
    assert daemon.vision.plan_action.call_args[0][0] == "click the third menu item"


def test_repeat_that_runs_the_last_command_again():
    daemon = _make_daemon()
    daemon.executor = MagicMock()
    daemon.handle_command("volume up")
    daemon.handle_command("repeat that")
    assert daemon.executor.execute_system_action.call_count == 2


@pytest.mark.parametrize("utterance", ["", "...", "!!!", "   ", "the a"])
def test_empty_or_punctuation_utterance_does_not_crash(utterance):
    """Empty/punctuation-only utterances exit cleanly instead of passing intent=None."""
    daemon = _make_daemon()
    daemon.executor = MagicMock()
    daemon.vision = MagicMock()
    daemon.handle_command(utterance)
    daemon.executor.execute_system_action.assert_not_called()
    daemon.vision.plan_action.assert_not_called()
    assert daemon._is_executing is False


def test_panic_vs_slow_vision_race_preserves_new_run_state():
    """Old worker finishing after panic + new command must not clear _is_executing."""
    import threading
    from src.vision.agent import VisionAction

    daemon = _make_daemon()
    daemon.capture = MagicMock()
    daemon.capture.grab_screen.return_value = (MagicMock(), 100, 100)
    daemon.executor = MagicMock()
    daemon.executor._get_active_window.return_value = 0

    old_entered = threading.Event()
    release_old = threading.Event()
    new_entered = threading.Event()
    release_new = threading.Event()
    captured_cancel_events = []

    call_count = 0

    def slow_plan(cmd, img, history=None, hwnd=0, cancel_event=None, **_kw):
        nonlocal call_count
        call_count += 1
        captured_cancel_events.append(cancel_event)
        if call_count == 1:
            old_entered.set()
            release_old.wait(timeout=3.0)
            return VisionAction(action="click", x=10, y=10, explanation="stale")
        new_entered.set()
        release_new.wait(timeout=3.0)
        return VisionAction(action="done", explanation="fresh done")

    daemon.vision = MagicMock()
    daemon.vision.plan_action.side_effect = slow_plan
    daemon.vision.execute_action.return_value = True

    t_old = threading.Thread(target=daemon.handle_command, args=("click stale button",), daemon=True)
    t_old.start()
    assert old_entered.wait(timeout=2.0)

    # Panic aborts old run and signals its cancel_event
    daemon.on_panic_key()
    assert captured_cancel_events[0] is not None
    assert captured_cancel_events[0].is_set()
    assert daemon._is_executing is False

    # Start a new command immediately while old worker is still blocked
    t_new = threading.Thread(target=daemon.handle_command, args=("click fresh button",), daemon=True)
    t_new.start()
    assert new_entered.wait(timeout=2.0)
    assert daemon._is_executing is True

    # Now let the old worker exit its finally block
    release_old.set()
    t_old.join(timeout=2.0)

    # New run must STILL own _is_executing
    assert daemon._is_executing is True

    # Finish new run cleanly
    release_new.set()
    t_new.join(timeout=2.0)
    assert daemon._is_executing is False
    daemon.vision.execute_action.assert_not_called()


def test_voice_feedback_tracking_and_continuous_rearm_waits_for_tts():
    """VoiceFeedback tracks active speech; continuous mode waits for TTS before re-arming."""
    import threading
    from src.tts.piper import VoiceFeedback

    tts = VoiceFeedback()
    started = threading.Event()
    release = threading.Event()

    def fake_speak(text):
        started.set()
        release.wait(timeout=2.0)

    tts._speak_sync = fake_speak
    assert tts.is_speaking is False
    tts.speak("hello world", asynchronous=True)
    assert started.wait(timeout=1.0)
    assert tts.is_speaking is True
    release.set()
    assert tts.wait_until_done(timeout=2.0) is True
    assert tts.is_speaking is False

    # Now test daemon._process_recording_worker waits for TTS
    daemon = _make_daemon()
    daemon.continuous = True
    daemon.tts = VoiceFeedback()
    tts_started = threading.Event()
    tts_release = threading.Event()

    def slow_tts(text):
        tts_started.set()
        tts_release.wait(timeout=2.0)

    daemon.tts._speak_sync = slow_tts
    daemon._transcribe_and_handle = lambda: daemon.tts.speak("saying something", asynchronous=True)

    rearmed = threading.Event()
    orig_toggle = daemon.on_listening_toggle

    def spy_toggle(state):
        orig_toggle(state)
        if state:
            rearmed.set()

    daemon.on_listening_toggle = spy_toggle

    worker = threading.Thread(target=daemon._process_recording_worker, daemon=True)
    worker.start()
    assert tts_started.wait(timeout=1.0)
    time.sleep(0.15)
    assert not rearmed.is_set()  # must NOT re-arm while TTS is speaking

    tts_release.set()
    assert rearmed.wait(timeout=2.0)
    worker.join(timeout=2.0)


@pytest.mark.parametrize("reply", [
    "yes please",
    "yes close this website only",
    "yeah do it",
    "go ahead and delete",
])
def test_guardrail_natural_confirm_phrases(reply):
    daemon = _make_daemon()
    daemon.executor = MagicMock()
    daemon.handle_command("close window")
    assert daemon._pending_confirmation == "close window"
    daemon.handle_command(reply)
    daemon.executor.execute_system_action.assert_called_once_with("window_close_active")
    assert daemon._pending_confirmation is None


@pytest.mark.parametrize("reply", ["no thanks", "cancel that"])
def test_guardrail_natural_cancel_phrases(reply):
    daemon = _make_daemon()
    daemon.executor = MagicMock()
    daemon.handle_command("close window")
    assert daemon._pending_confirmation == "close window"
    daemon.handle_command(reply)
    daemon.executor.execute_system_action.assert_not_called()
    assert daemon._pending_confirmation is None


def test_confirm_pending_method_resolves_guardrail():
    daemon = _make_daemon()
    daemon.executor = MagicMock()
    daemon.handle_command("close window")
    assert daemon._pending_confirmation == "close window"
    daemon.confirm_pending(False)
    daemon.executor.execute_system_action.assert_not_called()
    assert daemon._pending_confirmation is None

    daemon.handle_command("close window")
    daemon.confirm_pending(True)
    daemon.executor.execute_system_action.assert_called_once_with("window_close_active")
    assert daemon._pending_confirmation is None


def test_mid_vision_guardrail_resumes_approved_action(monkeypatch):
    """Confirming a mid-vision guardrail executes the parked action and continues the loop."""
    from src.vision.agent import VisionAction

    monkeypatch.setattr("main.time.sleep", lambda s: None)
    daemon = _make_daemon()
    daemon.capture = MagicMock()
    daemon.capture.grab_screen.return_value = (MagicMock(), 100, 100)
    daemon.executor = MagicMock()
    daemon.executor._get_active_window.return_value = 0

    step1 = VisionAction(action="click", x=10, y=10, explanation="open menu")
    step2 = VisionAction(action="click", x=20, y=20, explanation="delete the file")
    step3 = VisionAction(action="done", explanation="file deleted")

    daemon.vision = MagicMock()
    daemon.vision.plan_action.side_effect = [step1, step2, step3]
    daemon.vision.execute_action.return_value = True

    daemon.handle_command("remove old draft")
    # step1 executed, step2 parked on guardrail
    assert daemon.vision.execute_action.call_count == 1
    assert daemon._pending_confirmation == "remove old draft"
    assert daemon._pending_vision_context is not None

    # Confirming must execute step2 directly (not restart from step1) and then plan step3 -> done
    daemon.handle_command("yes please")
    assert daemon._pending_confirmation is None
    assert daemon._pending_vision_context is None
    assert daemon.vision.execute_action.call_count == 2
    assert daemon.vision.execute_action.call_args_list[1][0][0] == step2
    assert daemon.vision.plan_action.call_count == 3


def test_compound_splitting_preserves_trailing_payload_and():
    """"open notepad and type bread and butter" keeps "bread and butter" intact."""
    daemon = _make_daemon()
    daemon.vision = MagicMock()
    daemon.executor = MagicMock()
    daemon.handle_command("open notepad and type bread and butter")
    daemon.executor.launch_app.assert_called_once()
    assert daemon.executor.run_action.call_args[0][0].target == "bread and butter"
    daemon.vision.plan_action.assert_not_called()


def test_vision_loop_allows_three_consecutive_waits_and_uses_config_max_steps(monkeypatch):
    """Up to 3 consecutive 'wait' actions are allowed; 4th wait stops. Respects max_vision_steps."""
    from src.vision.agent import VisionAction

    monkeypatch.setattr("main.time.sleep", lambda s: None)
    daemon = _make_daemon()
    daemon.capture = MagicMock()
    daemon.capture.grab_screen.return_value = (MagicMock(), 100, 100)
    daemon.executor = MagicMock()
    daemon.executor._get_active_window.return_value = 0

    wait_act = VisionAction(action="wait", explanation="loading")
    done_act = VisionAction(action="done", explanation="loaded")
    daemon.vision = MagicMock()
    daemon.vision.plan_action.side_effect = [wait_act, wait_act, wait_act, done_act]
    daemon.handle_command("wait for page to finish")
    assert daemon.vision.plan_action.call_count == 4

    # 4 consecutive waits -> stops on the 4th
    daemon.vision.plan_action.side_effect = [wait_act, wait_act, wait_act, wait_act, done_act]
    daemon.handle_command("wait forever")
    assert daemon.vision.plan_action.call_count == 8  # 4 + 4

    # Respects config.max_vision_steps
    daemon.config.max_vision_steps = 3
    daemon.vision.plan_action.side_effect = [
        VisionAction(action="scroll", x=10, y=10, explanation=f"s{i}") for i in range(10)
    ]
    daemon.vision.execute_action.return_value = True
    daemon.handle_command("inspect every item on the canvas")
    assert daemon.vision.plan_action.call_count == 11  # 8 + 3


def test_recorder_on_level_wired_to_ui_set_audio_level(monkeypatch):
    """If UI provides set_audio_level and recorder has on_level, daemon wires them."""
    fake_ui = MagicMock()
    fake_ui.set_audio_level = MagicMock()
    fake_recorder = MagicMock()
    fake_recorder.on_level = None
    monkeypatch.setattr("main.AppShell", lambda **kw: fake_ui)
    monkeypatch.setattr("main.AudioRecorder", lambda **kw: fake_recorder)

    daemon = ComputerAutoDaemon(mock_stt=True, mock_vision=True, ui_mode="app")
    assert daemon.recorder.on_level is fake_ui.set_audio_level
