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
import re
import threading
import time
import winsound
from typing import Optional

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

try:
    from dotenv import load_dotenv
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.is_file():
        load_dotenv(dotenv_path=env_file)
except Exception:
    pass

from src.config import load_config
from src.audio.recorder import AudioRecorder
from src.trigger.hotkey import GlobalHotkeyListener
from src.stt.engine import SpeechRecognizer
from src.router.router import CommandRouter
from src.executor.windows import WindowsExecutor
from src.executor.guardrail import SafetyGuardrail
from src.vision.capture import ScreenCapture
from src.vision.agent import VisionAgent
from src.tts.piper import VoiceFeedback
from src.ui.hud import FloatingHUD
from src.ui.app import DesktopApp


class ComputerAutoDaemon:
    """Central daemon tying hotkeys, UI control center, speech, routing, and execution together."""

    # Spoken/typed replies that resolve a pending guardrail confirmation
    CONFIRM_WORDS = {
        "yes", "yeah", "yep", "yup", "confirm", "confirmed", "proceed",
        "do it", "sure", "go ahead", "ok", "okay", "affirmative",
    }
    MAX_VISION_STEPS = 8  # ponytail: fixed cap per command, make configurable if tasks need more
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

        # Check for explicit audio device index in environment
        dev_idx = None
        dev_env = os.environ.get("AUDIO_DEVICE_INDEX")
        if dev_env is not None and dev_env.strip().isdigit():
            dev_idx = int(dev_env.strip())

        self.recorder = AudioRecorder(sample_rate=self.config.sample_rate, device_index=dev_idx)
        self.recorder.on_silence = self._on_audio_silence_detected
        self.recognizer = SpeechRecognizer(
            model_dir=self.config.stt_model_dir, mock_mode=mock_stt
        )
        self.router = CommandRouter(intents=self.config.intents)
        self.executor = WindowsExecutor()
        self.guardrail = SafetyGuardrail()
        self.capture = ScreenCapture()
        self.vision = VisionAgent(
            model_name=self.config.vision_model, mock_mode=mock_vision
        )
        self.tts = VoiceFeedback()
        self._is_executing = False
        self._listening_lock = threading.Lock()
        self._listening_active = False
        self._pending_confirmation: Optional[str] = None
        self.continuous = False  # a listening session is active: re-arm the mic after every command

        self.hotkey_listener = GlobalHotkeyListener(
            threshold_ms=self.config.double_tap_threshold_ms,
            on_toggle=lambda _state: self.toggle_session(),
            on_panic=self.on_panic_key,
        )

        self.ui = None
        if self.ui_mode == "app":
            self.ui = DesktopApp(
                daemon=self,
                on_toggle_listening=self.on_ui_toggle_click,
                on_panic=self.on_panic_key,
                on_run_command=self.on_manual_command,
            )
            self.ui.init_ui()
        elif self.ui_mode == "hud":
            self.ui = FloatingHUD(
                on_toggle_click=self.on_ui_toggle_click,
                on_close=self.shutdown,
            )
            self.ui.init_ui()

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

    def _process_recording_worker(self) -> None:
        try:
            self._transcribe_and_handle()
        finally:
            if self.continuous:
                self.hotkey_listener.detector.is_listening = True
                self.on_listening_toggle(True)

    def _transcribe_and_handle(self) -> None:
        samples = self.recorder.stop()

        if len(samples) == 0:
            err_msg = self.recorder.last_error or "Audio buffer empty (silence or device unready)"
            print(f"[WARNING] No audio captured: {err_msg}")
            self.update_ui("ready", "Ready — No speech heard", err_msg[:45])
            self.ui_log(f"[AUDIO WARNING]: No audio captured -> {err_msg}")
            return

        text = self.recognizer.transcribe(samples, sample_rate=self.recorder.sample_rate)
        if not text:
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
        self._is_executing = False
        self._pending_confirmation = None
        with self._listening_lock:
            self._listening_active = False
        # Keep the hotkey detector in sync even when panic came from the UI,
        # otherwise the next double-tap toggles the wrong direction.
        self.hotkey_listener.detector.is_listening = False
        self.hotkey_listener.detector.last_tap_time = 0.0
        self.play_sound(400, 200)
        self.update_ui("ready", "Aborted (Panic Key)", "Action halted")
        self.ui_log("[PANIC]: Emergency stop triggered via Escape key.")

    def handle_command(self, utterance: str, confirmed: bool = False) -> None:
        """Process transcribed speech or typed command.

        A guardrail interception parks the utterance in _pending_confirmation;
        a follow-up "yes"/"confirm" re-enters here with confirmed=True, and
        "no"/"cancel" drops it. This makes destructive intents (e.g. close
        window) actually completable instead of a dead end.
        """
        if self._is_executing:
            print(f"[BUSY]: Action in progress, skipping \"{utterance}\"")
            self.ui_log(f"[BUSY]: Action in progress, please wait...")
            return

        self._is_executing = True
        try:
            # Resolve any pending guardrail confirmation first
            if self._pending_confirmation is not None and not confirmed:
                norm = " ".join(re.sub(r"[^\w\s]", "", utterance).lower().split())
                if norm in self.CONFIRM_WORDS:
                    pending = self._pending_confirmation
                    self._pending_confirmation = None
                    print(f"[GUARDRAIL]: Confirmed -> executing \"{pending}\"")
                    self.ui_log(f"[GUARDRAIL]: Confirmed -> executing \"{pending}\"")
                    utterance = pending
                    confirmed = True
                elif norm in self.CANCEL_WORDS:
                    self._pending_confirmation = None
                    print("[GUARDRAIL]: User cancelled the pending action.")
                    self.update_ui("ready", "Action cancelled", "Confirmation declined")
                    self.ui_log("[GUARDRAIL]: User cancelled the pending action.")
                    self.tts.speak("Action cancelled.")
                    return
                else:
                    # A different command supersedes the pending confirmation
                    self._pending_confirmation = None

            print(f"[UTTERANCE]: \"{utterance}\"")
            self.update_ui("processing", f"Routing: \"{utterance}\"", "Classifying intent...")
            self.ui_log(f"[COMMAND]: Processing \"{utterance}\"")

            route = self.router.route(utterance)

            # 1. Tier 1: Deterministic System Intent
            if not route.is_vision and route.intent is not None:
                intent = route.intent
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
                    return

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

                self.update_ui("ready", f"Executed: {intent.name}", f"\"{utterance}\"")

            # 2. Tier 2: Unscripted Visual Navigation via vision model
            else:
                print("[TIER 2 VISION]: Unscripted command -> routing to vision model...")
                self.update_ui("executing", "Vision Agent Planning...", "Analyzing screen with vision model...")
                self.ui_log("[TIER 2 VISION]: Routing to vision model...")

                # Look -> act -> look again, until the model says done. Panic clears _is_executing.
                history: list = []
                for step in range(1, self.MAX_VISION_STEPS + 1):
                    if not self._is_executing:
                        return
                    img, w, h = self.capture.grab_screen()
                    action = self.vision.plan_action(utterance, img, history)
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
                        self.update_ui("guardrail", "Confirmation Required", "Say 'yes' to confirm or 'no' to cancel")
                        self.ui_log(f"[GUARDRAIL]: {warning}")
                        self.tts.speak(warning)
                        return

                    self.update_ui("executing", f"Vision step {step}: {action.action}", action.explanation[:45])
                    ok = self.vision.execute_action(action)
                    history.append(f"{action.action}: {action.explanation}" + ("" if ok else " (FAILED)"))
                    time.sleep(1.0)  # let the screen settle before the next look

                self.update_ui("ready", "Vision stopped", f"Hit {self.MAX_VISION_STEPS}-step limit")
                self.ui_log(f"[TIER 2 VISION]: Stopped after {self.MAX_VISION_STEPS} steps.")
        finally:
            self._is_executing = False


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
