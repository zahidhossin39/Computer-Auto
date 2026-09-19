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
from src.vision.agent import GeminiVisionAgent
from src.tts.piper import VoiceFeedback
from src.ui.hud import FloatingHUD
from src.ui.app import DesktopApp


class ComputerAutoDaemon:
    """Central daemon tying hotkeys, UI control center, speech, routing, and execution together."""

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
        self.recognizer = SpeechRecognizer(
            model_dir=self.config.stt_model_dir, mock_mode=mock_stt
        )
        self.router = CommandRouter(intents=self.config.intents)
        self.executor = WindowsExecutor()
        self.guardrail = SafetyGuardrail()
        self.capture = ScreenCapture()
        self.vision = GeminiVisionAgent(
            model_name=self.config.gemini_model, mock_mode=mock_vision
        )
        self.tts = VoiceFeedback()
        self._is_executing = False

        self.hotkey_listener = GlobalHotkeyListener(
            threshold_ms=self.config.double_tap_threshold_ms,
            on_toggle=self.on_listening_toggle,
            on_panic=self.on_panic_key,
        )

        self.ui = None
        if self.ui_mode == "app":
            self.ui = DesktopApp(
                daemon=self,
                on_toggle_listening=self.on_ui_toggle_click,
                on_panic=self.on_panic_key,
                on_run_command=self.handle_command,
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

    def on_ui_toggle_click(self) -> None:
        """Invoked when user clicks the microphone button on the floating HUD pill."""
        new_state = not self.hotkey_listener.detector.is_listening
        self.hotkey_listener.detector.is_listening = new_state
        self.on_listening_toggle(new_state)

    def on_listening_toggle(self, is_listening: bool) -> None:
        """Invoked when listening state changes (via hotkey or UI click)."""
        if is_listening:
            self.play_sound(880, 100)
            print("\n[LISTENING] Recording audio... (Double-tap Left Ctrl or click Stop)")
            self.update_ui(
                "listening",
                "Listening... (Speak your command)",
                "Double-tap Ctrl or click Stop when done",
            )
            self.ui_log("[LISTENING]: Audio recording started...")
            self.recorder.start()
        else:
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
        samples = self.recorder.stop()

        if len(samples) == 0:
            err_msg = self.recorder.last_error or "Audio buffer empty (silence or device unready)"
            print(f"[WARNING] No audio captured: {err_msg}")
            self.update_ui("ready", "Ready — No speech heard", err_msg[:45])
            self.ui_log(f"[AUDIO WARNING]: No audio captured -> {err_msg}")
            return

        text = self.recognizer.transcribe(samples)
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
        self.recorder.stop()
        self._is_executing = False
        self.play_sound(400, 200)
        self.update_ui("ready", "Aborted (Panic Key)", "Action halted")
        self.ui_log("[PANIC]: Emergency stop triggered via Escape key.")

    def handle_command(self, utterance: str) -> None:
        """Process transcribed speech or typed command."""
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
            if self.guardrail.requires_confirmation(utterance, intent.is_destructive):
                warning = self.guardrail.format_confirmation_prompt(utterance)
                print(f"[GUARDRAIL]: {warning}")
                self.update_ui("guardrail", "Confirmation Required", warning)
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

        # 2. Tier 2: Unscripted Visual Navigation via Gemini Flash
        else:
            print("[TIER 2 VISION]: Unscripted command -> routing to Gemini Flash...")
            self.update_ui("executing", "Vision Agent Planning...", "Analyzing screen with Gemini Flash...")
            self.ui_log("[TIER 2 VISION]: Routing to Gemini Flash...")

            img, w, h = self.capture.grab_screen()
            print(f"[SCREEN CAPTURE]: Screen dimensions {w}x{h}")
            self.ui_log(f"[SCREEN CAPTURE]: Captured {w}x{h}")

            action = self.vision.plan_action(utterance, img)
            print(f"[AGENT PLAN]: Action='{action.action}', Target=({action.x}, {action.y}) | {action.explanation}")
            self.ui_log(f"[AGENT PLAN]: {action.action} at ({action.x}, {action.y}) -> {action.explanation}")

            # If Gemini was unable to plan an action or errored out
            if action.action == "none":
                print(f"[WARNING]: Visual navigation planning failed -> {action.explanation}")
                self.update_ui("ready", "Vision Action Failed", action.explanation[:45])
                self.ui_log(f"[TIER 2 VISION ERROR]: {action.explanation}")
                return

            if self.guardrail.requires_confirmation(action.explanation):
                warning = self.guardrail.format_confirmation_prompt(action.explanation)
                print(f"[GUARDRAIL]: {warning}")
                self.update_ui("guardrail", "Confirmation Required", warning)
                self.ui_log(f"[GUARDRAIL]: {warning}")
                self.tts.speak(warning)
                return

            self.update_ui("executing", f"Vision: {action.action}", action.explanation[:45])

            success = self.vision.execute_action(action)
            if success:
                print("[EXECUTED]: Visual action completed.")
                self.update_ui("ready", "Visual Action Completed", action.explanation[:45])
                self.ui_log(f"[EXECUTED]: Visual action completed -> {action.explanation}")
            else:
                print(f"[WARNING]: Visual action could not be executed: {action.explanation}")
                self.update_ui("ready", "Action not executable", action.explanation[:45])
                self.ui_log(f"[WARNING]: Visual action could not be executed: {action.explanation}")

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
        "--mock-vision", action="store_true", help="Use mock vision agent without calling Gemini API"
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
