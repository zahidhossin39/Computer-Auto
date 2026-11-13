# CRITICAL: Attach to user's interactive 'Default' desktop BEFORE any GUI/audio/hook imports!
import sys
if sys.platform == "win32":
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hDesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hDesk:
            user32.SetThreadDesktop(hDesk)
    except Exception:
        pass

import argparse
import inspect
import re
import threading
import time
import winsound
from typing import Callable, Optional

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
from pathlib import Path
from typing import Optional

from src.config import get_app_dir, load_config, load_settings

try:
    from dotenv import load_dotenv
    env_file = get_app_dir() / ".env"
    if env_file.is_file():
        load_dotenv(dotenv_path=env_file)
except Exception:
    pass
from src import apps
from src.audio.recorder import AudioRecorder
from src.trigger.hotkey import GlobalHotkeyListener
from src.stt.engine import SpeechRecognizer, download_parakeet_model
from src.router.router import CommandRouter
from src.executor.windows import WindowsExecutor
from src.executor.guardrail import SafetyGuardrail
from src.vision.capture import ScreenCapture
from src.vision.agent import VisionAgent
from src.tts.piper import VoiceFeedback
from src.ui.shell import AppShell


def _supports_kwarg(fn, name: str) -> bool:
    """Return True if callable `fn` accepts keyword argument `name`."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def _thumb(img):
    """Coarse fingerprint of the screen: equal thumbnails mean nothing visibly changed."""
    from PIL import Image
    if not isinstance(img, Image.Image):
        return None
    return img.convert("L").resize((48, 27)).point(lambda v: v // 16).tobytes()


class ComputerAutoDaemon:
    """Central daemon tying hotkeys, UI control center, speech, routing, and execution together."""

    # Spoken/typed replies that resolve a pending guardrail confirmation
    CONFIRM_WORDS = {
        "yes", "yeah", "yep", "yup", "confirm", "confirmed", "proceed",
        "do it", "sure", "go ahead", "ok", "okay", "affirmative",
    }
    MAX_VISION_STEPS = 8  # ponytail: fixed cap per command, make configurable if tasks need more
    REPEAT_WORDS = {"repeat", "repeat that", "again", "do that again", "do it again", "one more time"}
    CANCEL_WORDS = {
        "no", "nope", "cancel", "abort", "stop", "nevermind", "never mind", "dont", "don't",
    }

    def __init__(
        self,
        mock_stt: bool = False,
        mock_vision: bool = False,
        ui_mode: str = "app",
        show_hud: Optional[bool] = None,
    ):
        print("=" * 60)
        print(" Initializing Computer-Auto Voice Automation System")
        print("=" * 60)

        # Handle backward-compatible show_hud parameter
        if show_hud is not None:
            ui_mode = "hud" if show_hud else "none"

        self.ui_mode = ui_mode
        self.config = load_config()

        # The mic picked in Settings ("3: Microphone ..."), else AUDIO_DEVICE_INDEX
        saved_dev = load_settings().get("audio_device", "")
        dev_idx = int(saved_dev.split(":")[0]) if saved_dev[:1].isdigit() else None
        dev_env = os.environ.get("AUDIO_DEVICE_INDEX")
        if dev_env is not None and dev_env.strip().isdigit():
            dev_idx = int(dev_env.strip())

        self.recorder = AudioRecorder(sample_rate=self.config.sample_rate, device_index=dev_idx)
        self.recorder.on_silence = self._on_audio_silence_detected
        model_dir = Path(self.config.stt_model_dir)
        if not model_dir.is_absolute():
            model_dir = get_app_dir() / model_dir
        self.recognizer = SpeechRecognizer(
            model_dir=str(model_dir), mock_mode=mock_stt,
            cloud_model=self.config.stt_cloud_model,
        )
        self.router = CommandRouter(intents=self.config.intents, use_jev=self.config.use_jev)
        threading.Thread(target=apps.load, daemon=True).start()  # "open <app>" index, ~1s
        self.executor = WindowsExecutor()
        self.guardrail = SafetyGuardrail()
        self.capture = ScreenCapture()
        self.vision = VisionAgent(
            model_name=self.config.vision_model, mock_mode=mock_vision,
            api_key=self.config.vision_api_key or None, api_base=self.config.vision_api_base,
        )
        self.tts = VoiceFeedback()
        self._exec_lock = threading.Lock()
        self._is_executing = False
        self._run_id = 0
        self._cancel_event = threading.Event()
        self._listening_lock = threading.Lock()
        self._listening_active = False
        self._pending_confirmation: Optional[str] = None
        self._pending_vision_context: Optional[dict] = None
        self._download_lock = threading.Lock()
        self._download_cancel_event: Optional[threading.Event] = None
        self._last_command = ""  # for "repeat that"
        self.continuous = False  # a listening session is active: re-arm the mic after every command

        self.hotkey_listener = GlobalHotkeyListener(
            threshold_ms=self.config.double_tap_threshold_ms,
            on_toggle=lambda _state: self.toggle_session(),
            on_panic=self.on_panic_key,
        )

        self.ui = None
        if self.ui_mode in ("app", "hud"):  # "hud" kept as an alias for the old flag
            self.ui = AppShell(
                daemon=self,
                on_toggle_listening=self.on_ui_toggle_click,
                on_panic=self.on_panic_key,
                on_run_command=self.on_manual_command,
            )
            self.ui.init_ui()
            if hasattr(self.ui, "set_audio_level") and hasattr(self.recorder, "on_level"):
                self.recorder.on_level = self.ui.set_audio_level

        # Backward compatibility alias
        self.hud = self.ui

    def on_manual_command(self, cmd: str) -> None:
        """Handle manual command execution on a background thread so UI stays responsive."""
        threading.Thread(target=self.handle_command, args=(cmd,), daemon=True).start()

    def _on_audio_silence_detected(self) -> None:
        """Invoked when voice activity ended and silence is detected."""
        if self.recorder.is_recording or self.hotkey_listener.detector.is_listening:
            print("[VAD]: Speech finished — auto-stopping recording...")
            self.hotkey_listener.detector.is_listening = False
            self.on_listening_toggle(False)

    def _restore_if_minimised(self, hwnd: int) -> int:
        """A minimised window shows no elements and is not on screen, so the agent would
        act blind. Restore it and let it paint before we look."""
        try:
            import win32con
            import win32gui
            if hwnd and win32gui.IsIconic(hwnd):
                print("[VISION]: target window was minimised, restoring it")
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                for _ in range(10):  # wait for the restore, not a fixed guess
                    time.sleep(0.1)
                    if not win32gui.IsIconic(hwnd):
                        break
                time.sleep(0.25)  # and let it paint
        except Exception:
            pass
        return hwnd

    def _set_ui_visible(self, visible: bool) -> None:
        """Ghost our own window during a vision run: shrunk, half-faded, click-through.

        It used to withdraw entirely, which could leave the app invisible with no way back.
        """
        if hasattr(self.ui, "set_ghost"):
            self.ui.set_ghost(not visible)

    def update_ui(self, state: str, message: str, detail: str = "") -> None:
        """Thread-safe UI status update dispatching to active UI."""
        if self.ui:
            self.ui.update_state(state, message, detail)

    def ui_log(self, message: str) -> None:
        """Log message to visible app console if available."""
        if hasattr(self.ui, "log"):
            self.ui.log(message)

    def play_sound(self, frequency: int, duration_ms: int = 80) -> None:
        """Play feedback audio chime."""
        try:
            winsound.Beep(frequency, duration_ms)
        except Exception:
            pass

    def toggle_session(self) -> None:
        """Double-tap / mic button: start a listening session, or end the running one.

        A session keeps listening and runs each command as it is spoken; the
        detector's own flip-flop state is ignored so a tap during processing
        ends the session instead of desyncing.
        """
        self.continuous = not self.continuous
        self.hotkey_listener.detector.is_listening = self.continuous
        print(f"[SESSION]: {'started' if self.continuous else 'ended'}")
        self.ui_log(f"[SESSION]: {'started' if self.continuous else 'ended'}")
        if self.continuous:
            self.play_sound(880, 100)
        self.on_listening_toggle(self.continuous)

    on_ui_toggle_click = toggle_session

    def on_listening_toggle(self, is_listening: bool) -> None:

        """Invoked when listening state changes (via hotkey or UI click).

        Idempotent: duplicate toggles (e.g. VAD auto-stop racing a manual
        double-tap stop) are ignored so only one transcription worker runs.
        """
        with self._listening_lock:
            if is_listening == self._listening_active:
                return
            self._listening_active = is_listening

        if is_listening:
            if not self.continuous:  # no beep spam while looping
                self.play_sound(880, 100)
            print("\n[LISTENING] Recording audio... (Double-tap Left Ctrl or click Stop)")
            self.update_ui(
                "listening",
                "Listening... (Speak your command)",
                "Double-tap Ctrl or click Stop when done",
            )
            self.ui_log("[LISTENING]: Audio recording started...")
            self.recorder.on_silence = self._on_audio_silence_detected
            self.recorder.start()
            if self.recorder.last_error:
                print(f"[AUDIO WARNING]: {self.recorder.last_error}")
                self.ui_log(f"[AUDIO WARNING]: {self.recorder.last_error}")
            if not self.recorder.is_recording:
                # Mic failed to open: revert listening state so the next
                # double-tap/click starts cleanly instead of toggling the wrong way.
                with self._listening_lock:
                    self._listening_active = False
                self.hotkey_listener.detector.is_listening = False
                self.continuous = False  # else the session looks on with nothing listening
                self.update_ui(
                    "error",
                    "Microphone failed to start",
                    (self.recorder.last_error or "Unknown audio error")[:45],
                )
        else:
            if not self.continuous:
                self.play_sound(550, 100)
            print("[PROCESSING] Transcribing speech utterance...")
            self.update_ui(
                "processing",
                "Processing Speech...",
                "Transcribing audio with Parakeet TDT...",
            )
            self.ui_log("[PROCESSING]: Transcribing speech...")
            # Process in worker thread so UI never freezes
            threading.Thread(target=self._process_recording_worker, daemon=True).start()

    def _wait_for_tts_before_rearm(self) -> None:
        """Wait for active TTS speech plus a short acoustic tail before re-arming the mic."""
        tts = getattr(self, "tts", None)
        if tts is None:
            return
        is_speaking = getattr(tts, "is_speaking", False)
        if isinstance(is_speaking, bool) and is_speaking:
            wait_fn = getattr(tts, "wait_until_done", None)
            if callable(wait_fn):
                deadline = time.monotonic() + 10.0
                while self.continuous and time.monotonic() < deadline:
                    if wait_fn(timeout=0.1):
                        break
            tail_end = time.monotonic() + 0.25
            while self.continuous and time.monotonic() < tail_end:
                time.sleep(0.05)

    def _process_recording_worker(self) -> None:
        try:
            self._transcribe_and_handle()
        finally:
            if self.continuous:
                self._wait_for_tts_before_rearm()
            if self.continuous:
                self.hotkey_listener.detector.is_listening = True
                self.on_listening_toggle(True)

    def download_offline_model(
        self, progress_cb: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        """Download and load the offline Parakeet STT model, preventing overlapping runs."""
        if not self._download_lock.acquire(blocking=False):
            self.ui_log("[STT]: Offline model download already in progress.")
            return False

        cancel_ev = threading.Event()
        self._download_cancel_event = cancel_ev
        try:
            raw_dir = getattr(self.recognizer, "model_dir", None)
            if raw_dir:
                target_dir = Path(raw_dir)
            elif self.config.stt_model_dir:
                target_dir = Path(self.config.stt_model_dir)
            else:
                target_dir = Path("models") / "parakeet-tdt-0.6b-int8"
            if not target_dir.is_absolute():
                target_dir = get_app_dir() / target_dir

            self.recognizer.model_dir = target_dir
            download_parakeet_model(target_dir, progress_cb=progress_cb, cancel_event=cancel_ev)
            ok = bool(self.recognizer.reload_local_model())
            self.update_ui(
                "ready",
                "Offline voice model ready" if ok else "Offline model setup incomplete",
            )
            self.ui_log(
                "[STT]: Offline Parakeet model ready." if ok else "[STT]: Offline model files downloaded, reload incomplete."
            )
            return ok
        except InterruptedError:
            self.ui_log("[STT]: Offline model download canceled.")
            self.update_ui("ready", "Download canceled")
            return False
        except Exception as e:
            print(f"[STT]: Model download failed: {e}")
            self.ui_log(f"[STT]: Model download failed: {e}")
            self.update_ui("ready", "Model download failed", str(e)[:45])
            return False
        finally:
            self._download_cancel_event = None
            self._download_lock.release()

    def cancel_model_download(self) -> None:
        """Signal any active offline model download to cancel."""
        ev = self._download_cancel_event
        if ev is not None:
            ev.set()

    def _transcribe_and_handle(self) -> None:
        samples = self.recorder.stop()

        if len(samples) == 0:
            err_msg = self.recorder.last_error or "Audio buffer empty (silence or device unready)"
            print(f"[WARNING] No audio captured: {err_msg}")
            self.update_ui("ready", "Ready — No speech heard", err_msg[:45])
            self.ui_log(f"[AUDIO WARNING]: No audio captured -> {err_msg}")
            return

        if not getattr(self.recognizer, "is_ready", True):
            msg = "Offline voice model not downloaded — download in Settings or pick Cloud STT"
            print(f"[STT]: {msg}")
            self.update_ui("ready", msg, "Open Settings to download")
            self.ui_log(f"[STT]: {msg}")
            return

        text = self.recognizer.transcribe(samples, sample_rate=self.recorder.sample_rate)
        if not text:
            if not getattr(self.recognizer, "is_ready", True):
                msg = "Offline voice model not downloaded — download in Settings or pick Cloud STT"
                self.update_ui("ready", msg, "Open Settings to download")
                self.ui_log(f"[STT]: {msg}")
                return
            print("[WARNING] Could not recognize speech.")
            self.update_ui("ready", "Ready — Could not recognize audio", "Speak clearly into mic")
            self.ui_log("[STT]: No speech recognized (silence or low volume).")
            return

        if hasattr(self.ui, "set_transcript"):
            self.ui.set_transcript(text)
        self.ui_log(f"[STT TRANSCRIPTION]: \"{text}\"")
        self.handle_command(text)

    def on_panic_key(self) -> None:
        """Invoked when user presses Escape."""
        print("\n[PANIC] Emergency stop triggered! Stopping all actions.")
        self.continuous = False  # panic always ends the session
        self.recorder.stop()
        with self._exec_lock:
            self._run_id += 1
            self._cancel_event.set()
            self._is_executing = False
        self._pending_confirmation = None
        self._pending_vision_context = None
        if hasattr(self.tts, "stop"):
            self.tts.stop()
        with self._listening_lock:
            self._listening_active = False
        # Keep the hotkey detector in sync even when panic came from the UI,
        # otherwise the next double-tap toggles the wrong direction.
        self.hotkey_listener.detector.is_listening = False
        self.hotkey_listener.detector.last_tap_time = 0.0
        self._set_ui_visible(True)
        self.play_sound(400, 200)
        self.update_ui("ready", "Aborted (Panic Key)", "Action halted")
        self.ui_log("[PANIC]: Emergency stop triggered via Escape key.")

    def _run_intent(self, intent, utterance: str, confirmed: bool) -> bool:
        """Execute one deterministic intent. False means it now waits for a spoken "yes"."""
        print(f"[TIER 1 ROUTER]: Matched intent '{intent.name}' ({intent.category})")
        self.ui_log(f"[TIER 1 ROUTER]: Matched intent '{intent.name}' ({intent.category})")

        # Check Guardrails
        if not confirmed and self.guardrail.requires_confirmation(utterance, intent.is_destructive):
            warning = self.guardrail.format_confirmation_prompt(utterance)
            print(f"[GUARDRAIL]: {warning}")
            self._pending_confirmation = utterance
            self.update_ui("guardrail", "Confirmation Required", "Say 'yes' to confirm or 'no' to cancel")
            self.ui_log(f"[GUARDRAIL]: {warning}")
            self.tts.speak(warning)
            return False

        # Execute action
        self.update_ui(
            "executing",
            f"Executing: {intent.name}",
            f"Command: {intent.action.command or intent.action.target}",
        )

        if intent.action.type == "system_action" and intent.action.command:
            self.executor.execute_system_action(intent.action.command)
            print(f"[EXECUTED]: Action '{intent.action.command}' dispatched.")
            self.ui_log(f"[EXECUTED]: Dispatched '{intent.action.command}'")
        elif intent.action.type == "launch_app":
            success = self.executor.launch_app(intent.action)
            if success:
                print(f"[EXECUTED]: Launched '{intent.action.target}'.")
                self.ui_log(f"[EXECUTED]: Launched '{intent.action.target}'")
            else:
                print(f"[ERROR]: Could not launch '{intent.action.target}'.")
                self.ui_log(f"[ERROR]: Failed to launch '{intent.action.target}'")
        elif intent.action.type == "say":
            print(f"[ANSWER]: {intent.action.target}")
            self.ui_log(f"[ANSWER]: {intent.action.target}")
            self.tts.speak(intent.action.target)
        elif intent.action.type in (
            "hotkey", "open_app", "type_text", "open_url",
            "focus_window", "close_window", "minimize_window", "maximize_window", "restore_window",
        ):
            ok = self.executor.run_action(intent.action)
            print(f"[EXECUTED]: {intent.action.type} {intent.action.keys or intent.action.command or intent.action.target} ({'ok' if ok else 'failed'})")
            self.ui_log(f"[EXECUTED]: {intent.name} ({'ok' if ok else 'failed'})")

        self.update_ui("ready", f"Executed: {intent.name}", f"\"{utterance}\"")
        return True

    def _settle(self, step) -> None:
        """Give a just-launched app time to open and take focus before the next step."""
        time.sleep(2.0 if step.intent.action.type in ("launch_app", "open_app", "open_url") else 0.3)

    _TRAILING_PAYLOAD_RE = re.compile(
        r"^(?:type|dictate|google|search\s+google\s+for|search\s+web\s+for|look\s+up|search\s+\w+\s+for)\s+.+",
        re.I,
    )
    _COMPOUND_SEP_RE = re.compile(r"\s*,?\s*\b(?:and then|then|and)\b\s*", re.I)

    def _split_compound(self, utterance: str) -> tuple:
        """"open chrome and search for cats" -> ([open chrome], "search for cats"): the known
        leading parts run instantly, only the rest goes to the vision agent.

        Once a segment begins a trailing-payload command (e.g. "type ...", "google ..."),
        the entire remainder of the utterance stays attached so internal "and"s are preserved.
        """
        seps = list(self._COMPOUND_SEP_RE.finditer(utterance))
        if not seps:
            return [], utterance
        known = []
        pos = 0
        for sep in seps:
            segment = utterance[pos:sep.start()].strip()
            if not segment:
                pos = sep.end()
                continue
            if self._TRAILING_PAYLOAD_RE.match(segment):
                remainder = utterance[pos:].strip()
                r = self.router.route(remainder)
                if r.is_vision or not r.intent:
                    return known, remainder if known else utterance
                known.append(r)
                return known, ""
            r = self.router.route(segment)
            if r.is_vision or not r.intent:
                return known, utterance[pos:].strip() if known else utterance
            known.append(r)
            pos = sep.end()

        tail = utterance[pos:].strip()
        if tail:
            r = self.router.route(tail)
            if r.is_vision or not r.intent:
                return known, tail if known else utterance
            known.append(r)
        return known, ""

    def _classify_confirmation(self, utterance: str) -> Optional[bool]:
        """Classify a spoken/typed reply to a pending guardrail prompt.

        Returns True to confirm, False to cancel, or None if it is an unrelated command.
        """
        norm = " ".join(re.sub(r"[^\w\s]", "", utterance).lower().split())
        if not norm:
            return None
        if norm in self.CONFIRM_WORDS:
            return True
        if norm in self.CANCEL_WORDS:
            return False
        for phrase in ("go ahead", "do it"):
            if norm.startswith(phrase + " "):
                return True
        for phrase in ("never mind", "do not", "dont", "stop it", "stop that"):
            if norm.startswith(phrase + " "):
                return False
        first = norm.split()[0]
        if first in {"yes", "yeah", "yep", "yup", "confirm", "confirmed", "proceed", "sure", "ok", "okay", "affirmative"}:
            return True
        if first in {"no", "nope", "cancel", "abort", "nevermind"}:
            return False
        return None

    def confirm_pending(self, approved: bool, asynchronous: Optional[bool] = None) -> None:
        """Resolve a pending guardrail confirmation from UI buttons or external callers."""
        if self._pending_confirmation is None:
            return
        reply = "yes" if approved else "no"
        if asynchronous is None:
            asynchronous = self.ui is not None
        if asynchronous:
            threading.Thread(target=self.handle_command, args=(reply,), daemon=True).start()
        else:
            self.handle_command(reply)

    def _is_run_active(self, run_id: int, cancel_event: threading.Event) -> bool:
        return not cancel_event.is_set() and self._is_executing and self._run_id == run_id

    def _sleep_interruptible(self, seconds: float, run_id: int, cancel_event: threading.Event) -> bool:
        steps = max(1, int(round(seconds / 0.1)))
        step_len = seconds / steps
        for _ in range(steps):
            if not self._is_run_active(run_id, cancel_event):
                return False
            time.sleep(step_len)
        return self._is_run_active(run_id, cancel_event)

    def _run_vision_loop(
        self,
        utterance: str,
        run_id: int,
        cancel_event: threading.Event,
        confirmed: bool = False,
        pending_ctx: Optional[dict] = None,
    ) -> None:
        """Execute Tier 2 visual navigation loop with panic cancellation and mid-loop guardrail support."""
        print("[TIER 2 VISION]: Unscripted command -> routing to vision model...")
        self.update_ui("executing", "Vision Agent Planning...", "Analyzing screen with vision model...")
        self.ui_log("[TIER 2 VISION]: Routing to vision model...")

        # Our Control Center is always-on-top: in the screenshot it covered the
        # target window, and the model kept "waiting for Computer-Auto to finish".
        self._set_ui_visible(False)

        if pending_ctx is not None:
            history = list(pending_ctx.get("history", []))
            seen = set(pending_ctx.get("seen", ()))
            start_step = int(pending_ctx.get("step", 1))
            prev_thumb = pending_ctx.get("prev_thumb")
            approved_action = pending_ctx.get("action")
        else:
            history = []
            seen = set()
            start_step = 1
            prev_thumb = None
            approved_action = None

        cfg_steps = getattr(self.config, "max_vision_steps", self.MAX_VISION_STEPS)
        max_steps = cfg_steps if isinstance(cfg_steps, int) and cfg_steps > 0 else self.MAX_VISION_STEPS
        consecutive_waits = 0
        supports_grab_hwnd = _supports_kwarg(self.capture.grab_screen, "hwnd")
        supports_origin = _supports_kwarg(self.vision.plan_action, "origin")
        supports_cancel = _supports_kwarg(self.vision.plan_action, "cancel_event")

        for step in range(start_step, max_steps + 1):
            if not self._is_run_active(run_id, cancel_event):
                return

            if approved_action is not None:
                action = approved_action
                approved_action = None
            else:
                # Re-read the target window every step: a click may open or focus a new one
                hwnd = self.executor._get_active_window() or 0
                hwnd = self._restore_if_minimised(hwnd)
                if supports_grab_hwnd:
                    img, w, h = self.capture.grab_screen(hwnd=hwnd)
                else:
                    img, w, h = self.capture.grab_screen()
                origin = getattr(self.capture, "last_origin", (0, 0))
                if not isinstance(origin, tuple) or len(origin) != 2:
                    origin = (0, 0)
                # Tell the model when its last action changed nothing it can see, so it
                # tries something else instead of assuming it worked.
                thumb = _thumb(img)
                if history and prev_thumb is not None and thumb is not None and prev_thumb == thumb:
                    history[-1] += " (the screen did not change)"
                prev_thumb = thumb
                plan_kwargs = {"hwnd": hwnd}
                if supports_origin:
                    plan_kwargs["origin"] = origin
                if supports_cancel:
                    plan_kwargs["cancel_event"] = cancel_event
                action = self.vision.plan_action(utterance, img, history, **plan_kwargs)
                if not self._is_run_active(run_id, cancel_event):  # Esc while the model was thinking: don't act
                    return

            print(f"[AGENT STEP {step}]: {action.action} at ({action.x}, {action.y}) | {action.explanation}")
            self.ui_log(f"[AGENT STEP {step}]: {action.action} at ({action.x}, {action.y}) -> {action.explanation}")

            if action.action == "done":
                self.update_ui("ready", "Visual Task Completed", action.explanation[:45])
                return
            if action.action == "none":
                self.update_ui("ready", "Vision Action Failed", action.explanation[:45])
                self.ui_log(f"[TIER 2 VISION ERROR]: {action.explanation}")
                return

            if not confirmed and self.guardrail.requires_confirmation(action.explanation):
                warning = self.guardrail.format_confirmation_prompt(action.explanation)
                print(f"[GUARDRAIL]: {warning}")
                self._pending_confirmation = utterance
                self._pending_vision_context = {
                    "command": utterance,
                    "action": action,
                    "history": list(history),
                    "seen": set(seen),
                    "step": step,
                    "prev_thumb": prev_thumb,
                }
                self.update_ui("guardrail", "Confirmation Required", "Say 'yes' to confirm or 'no' to cancel")
                self.ui_log(f"[GUARDRAIL]: {warning}")
                self.tts.speak(warning)
                return

            if action.action == "wait":
                consecutive_waits += 1
                if consecutive_waits > 3:
                    print("[TIER 2 VISION]: waited too many times, stopping.")
                    self.update_ui("ready", "Stopped: action had no effect", action.explanation[:45])
                    self.ui_log("[TIER 2 VISION]: Consecutive waits exceeded limit -> stopped.")
                    return
                history.append(f"wait: {action.explanation}")
                if not self._sleep_interruptible(1.0, run_id, cancel_event):
                    return
                continue

            consecutive_waits = 0

            # Action signature: accurately identify duplicates across different action types
            if action.action == "type":
                sig = ("type", action.text, action.x, action.y)
            elif action.action == "hotkey":
                sig = ("hotkey", tuple(action.keys))
            elif action.action == "scroll":
                sig = ("scroll", action.direction)
            else:
                sig = (action.action, action.x, action.y)

            # proposed before: it already happened or does nothing (scrolling on is fine)
            if sig in seen and action.action != "scroll":
                print("[TIER 2 VISION]: same action had no effect, stopping.")
                self.update_ui("ready", "Stopped: action had no effect", action.explanation[:45])
                self.ui_log("[TIER 2 VISION]: Same action repeated with no effect -> stopped.")
                return

            self.update_ui("executing", f"Vision step {step}: {action.action}", action.explanation[:45])
            ok = self.vision.execute_action(action)
            seen.add(sig)
            if ok and action.final:
                print("[TIER 2 VISION]: final action done.")
                self.update_ui("ready", "Visual Task Completed", action.explanation[:45])
                return
            history.append(f"{action.action}: {action.explanation}" + ("" if ok else " (FAILED)"))
            if not self._sleep_interruptible(0.5, run_id, cancel_event):
                return

        self.update_ui("ready", "Vision stopped", f"Hit {max_steps}-step limit")
        self.ui_log(f"[TIER 2 VISION]: Stopped after {max_steps} steps.")

    def handle_command(self, utterance: str, confirmed: bool = False) -> None:
        """Process transcribed speech or typed command.

        A guardrail interception parks the utterance in _pending_confirmation;
        a follow-up "yes"/"confirm" re-enters here with confirmed=True, and
        "no"/"cancel" drops it. This makes destructive intents (e.g. close
        window) actually completable instead of a dead end.
        """
        with self._exec_lock:
            if self._is_executing:
                print(f"[BUSY]: Action in progress, skipping \"{utterance}\"")
                self.ui_log(f"[BUSY]: Action in progress, please wait...")
                return
            self._is_executing = True
            self._run_id += 1
            run_id = self._run_id
            cancel_event = threading.Event()
            self._cancel_event = cancel_event

        try:
            pending_vision_ctx = None
            # Resolve any pending guardrail confirmation first
            if self._pending_confirmation is not None and not confirmed:
                decision = self._classify_confirmation(utterance)
                if decision is True:
                    pending = self._pending_confirmation
                    pending_vision_ctx = self._pending_vision_context
                    self._pending_confirmation = None
                    self._pending_vision_context = None
                    print(f"[GUARDRAIL]: Confirmed -> executing \"{pending}\"")
                    self.ui_log(f"[GUARDRAIL]: Confirmed -> executing \"{pending}\"")
                    utterance = pending
                    confirmed = True
                elif decision is False:
                    self._pending_confirmation = None
                    self._pending_vision_context = None
                    print("[GUARDRAIL]: User cancelled the pending action.")
                    self.update_ui("ready", "Action cancelled", "Confirmation declined")
                    self.ui_log("[GUARDRAIL]: User cancelled the pending action.")
                    self.tts.speak("Action cancelled.")
                    return
                else:
                    # A different command supersedes the pending confirmation
                    self._pending_confirmation = None
                    self._pending_vision_context = None

            if pending_vision_ctx is not None:
                self._run_vision_loop(
                    utterance, run_id, cancel_event, confirmed=True, pending_ctx=pending_vision_ctx
                )
                return

            norm = " ".join(re.sub(r"[^\w\s]", "", utterance).lower().split())
            if norm in self.REPEAT_WORDS:
                if not self._last_command:
                    self.ui_log("[ANSWER]: Nothing to repeat yet")
                    return
                utterance = self._last_command
            elif norm:
                self._last_command = utterance
            print(f"[UTTERANCE]: \"{utterance}\"")
            self.update_ui("processing", f"Routing: \"{utterance}\"", "Classifying intent...")
            self.ui_log(f"[COMMAND]: Processing \"{utterance}\"")

            route = self.router.route(utterance)
            if not route.is_vision and route.intent is None:
                self.update_ui("ready", "Ready — No command heard", "")
                return

            # 1. Tier 1: deterministic intents - one, or a chain like "open notepad and type hi"
            steps, rest = ([route], "") if not route.is_vision else self._split_compound(utterance)
            for i, r in enumerate(steps):
                if not self._is_run_active(run_id, cancel_event):
                    return
                if i:
                    self._settle(steps[i - 1])
                if not self._run_intent(r.intent, r.command, confirmed):
                    return
            if steps and rest:
                self._settle(steps[-1])
                utterance = rest
                print(f"[TIER 2 VISION]: rest of the command: \"{rest}\"")

            # 2. Tier 2: Unscripted Visual Navigation via vision model
            if rest:
                self._run_vision_loop(utterance, run_id, cancel_event, confirmed=confirmed)
        finally:
            is_current = False
            with self._exec_lock:
                if self._run_id == run_id:
                    self._is_executing = False
                    is_current = True
            if is_current:
                self._set_ui_visible(True)


    def shutdown(self) -> None:
        """Clean shutdown."""
        self.hotkey_listener.stop()
        print("\nShutting down Computer-Auto...")

    def run(self, interactive_repl: bool = False) -> None:
        """Start daemon loop."""
        self.hotkey_listener.start()
        print("\n[ACTIVE] Computer-Auto is running!")
        print("  -> Press [Double-Tap Left Ctrl] OR click the UI button to speak.")
        print("  -> Press [Escape] at any time as the Panic Key.")
        print("  -> Press [Ctrl + C] in this console to exit.")

        if self.ui:
            if not getattr(self.recognizer, "is_ready", True):
                self.update_ui(
                    "ready",
                    "Offline voice model missing — open Settings to download",
                    "Typed commands still work",
                )
            try:
                self.ui.mainloop()
            except KeyboardInterrupt:
                pass
            self.shutdown()
            return

        if interactive_repl:
            print("\n[INTERACTIVE] Text Mode active (Type commands and hit Enter):")
            try:
                while True:
                    cmd = input("\nComputer-Auto> ").strip()
                    if not cmd:
                        continue
                    if cmd.lower() in ["exit", "quit"]:
                        break
                    self.handle_command(cmd)
            except KeyboardInterrupt:
                pass
        else:
            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass

        self.shutdown()


def main():
    class _TeeStdout:
        """Mirror every print to both the console and logs/app.log."""

        def __init__(self, stream):
            self._stream = stream
            log_dir = get_app_dir() / "logs"
            log_dir.mkdir(exist_ok=True)
            self._log = open(log_dir / "app.log", "a", encoding="utf-8", buffering=1)

        def write(self, message):
            self._stream.write(message)
            self._log.write(message)

        def flush(self):
            self._stream.flush()
            self._log.flush()

        def __getattr__(self, name):
            return getattr(self._stream, name)

    sys.stdout = _TeeStdout(sys.stdout)

    parser = argparse.ArgumentParser(description="Computer-Auto Voice Automation Engine")
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Run interactive terminal command loop without GUI"
    )
    parser.add_argument(
        "--mock-stt", action="store_true", help="Use mock STT engine without loading weights"
    )
    parser.add_argument(
        "--mock-vision", action="store_true", help="Use mock vision agent without calling the vision API"
    )
    parser.add_argument(
        "--hud", action="store_true", help="Use mini floating HUD pill instead of Desktop Control Center"
    )
    parser.add_argument(
        "--no-ui", "--no-hud", action="store_true", help="Disable all visual GUI interfaces"
    )
    args = parser.parse_args()

    if args.interactive or args.no_ui:
        ui_mode = "none"
    elif args.hud:
        ui_mode = "hud"
    else:
        ui_mode = "app"

    daemon = ComputerAutoDaemon(
        mock_stt=args.mock_stt,
        mock_vision=args.mock_vision,
        ui_mode=ui_mode,
    )
    daemon.run(interactive_repl=args.interactive)


if __name__ == "__main__":
    main()
