"""Computer-Auto: Voice-controlled desktop automation daemon with Floating HUD."""

import argparse
import sys
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

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
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


class ComputerAutoDaemon:
    """Central daemon tying hotkeys, HUD pill, speech, routing, and execution together."""

    def __init__(
        self,
        mock_stt: bool = False,
        mock_vision: bool = False,
        show_hud: bool = True,
    ):
        print("=" * 60)
        print(" Initializing Computer-Auto Voice Automation System")
        print("=" * 60)

        self.config = load_config()
        self.recorder = AudioRecorder(sample_rate=self.config.sample_rate)
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

        self.hud: Optional[FloatingHUD] = None
        if show_hud:
            self.hud = FloatingHUD(
                on_toggle_click=self.on_ui_toggle_click,
                on_close=self.shutdown,
            )
            self.hud.init_ui()

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
        """Invoked when listening state changes (via hotkey or HUD click)."""
        if is_listening:
            self.play_sound(880, 100)
            print("\n[LISTENING] Recording audio... (Double-tap Left Ctrl or click Stop)")
            if self.hud:
                self.hud.update_state(
                    "listening",
                    "Listening... (Speak your command)",
                    "Double-tap Ctrl or click Stop when done",
                )
            self.recorder.start()
        else:
            self.play_sound(550, 100)
            print("[PROCESSING] Transcribing speech utterance...")
            if self.hud:
                self.hud.update_state(
                    "processing",
                    "Processing Speech...",
                    "Transcribing audio with Parakeet...",
                )
            # Process in worker thread so UI never freezes
            threading.Thread(target=self._process_recording_worker, daemon=True).start()

    def _process_recording_worker(self) -> None:
        samples = self.recorder.stop()

        if len(samples) == 0:
            print("[WARNING] No audio captured.")
            if self.hud:
                self.hud.update_state("ready", "Ready — No speech heard", "Try speaking again")
            return

        text = self.recognizer.transcribe(samples)
        if not text:
            print("[WARNING] Could not recognize speech.")
            if self.hud:
                self.hud.update_state("ready", "Ready — Could not recognize audio", "Speak clearly into mic")
            return

        self.handle_command(text)

    def on_panic_key(self) -> None:
        """Invoked when user presses Escape."""
        print("\n[PANIC] Emergency stop triggered! Stopping all actions.")
        self.recorder.stop()
        self._is_executing = False
        self.play_sound(400, 200)
        if self.hud:
            self.hud.update_state("ready", "Aborted (Panic Key)", "Action halted")

    def handle_command(self, utterance: str) -> None:
        """Process transcribed speech or typed command."""
        print(f"[UTTERANCE]: \"{utterance}\"")
        if self.hud:
            self.hud.update_state("processing", f"Routing: \"{utterance}\"", "Classifying intent...")

        route = self.router.route(utterance)

        # 1. Tier 1: Deterministic System Intent
        if not route.is_vision and route.intent is not None:
            intent = route.intent
            print(f"[TIER 1 ROUTER]: Matched intent '{intent.name}' ({intent.category})")

            # Check Guardrails
            if self.guardrail.requires_confirmation(utterance, intent.is_destructive):
                warning = self.guardrail.format_confirmation_prompt(utterance)
                print(f"[GUARDRAIL]: {warning}")
                if self.hud:
                    self.hud.update_state("guardrail", "Confirmation Required", warning)
                self.tts.speak(warning)
                return

            # Execute action
            if self.hud:
                self.hud.update_state("executing", f"Executing: {intent.name}", f"Command: {intent.action.command or intent.action.target}")

            if intent.action.type == "system_action" and intent.action.command:
                self.executor.execute_system_action(intent.action.command)
                print(f"[EXECUTED]: Action '{intent.action.command}' dispatched.")
            elif intent.action.type == "launch_app":
                success = self.executor.launch_app(intent.action)
                if success:
                    print(f"[EXECUTED]: Launched '{intent.action.target}'.")
                else:
                    print(f"[ERROR]: Could not launch '{intent.action.target}'.")

            if self.hud:
                self.hud.update_state("ready", f"Executed: {intent.name}", f"\"{utterance}\"")

        # 2. Tier 2: Unscripted Visual Navigation via Gemini Flash
        else:
            print("[TIER 2 VISION]: Unscripted command -> routing to Gemini Flash...")
            if self.hud:
                self.hud.update_state("executing", "Vision Agent Planning...", "Analyzing screen with Gemini...")

            img, w, h = self.capture.grab_screen()
            print(f"[SCREEN CAPTURE]: Screen dimensions {w}x{h}")

            action = self.vision.plan_action(utterance, img)
            print(f"[AGENT PLAN]: Action='{action.action}', Target=({action.x}, {action.y}) | {action.explanation}")

            if self.guardrail.requires_confirmation(action.explanation):
                warning = self.guardrail.format_confirmation_prompt(action.explanation)
                print(f"[GUARDRAIL]: {warning}")
                if self.hud:
                    self.hud.update_state("guardrail", "Confirmation Required", warning)
                self.tts.speak(warning)
                return

            if self.hud:
                self.hud.update_state("executing", f"Vision: {action.action}", action.explanation[:45])

            success = self.vision.execute_action(action)
            if success:
                print("[EXECUTED]: Visual action completed.")
                if self.hud:
                    self.hud.update_state("ready", "Visual Action Completed", action.explanation[:45])
            else:
                print("[WARNING]: Visual action could not be executed.")
                if self.hud:
                    self.hud.update_state("ready", "Action not executable", action.explanation[:45])

    def shutdown(self) -> None:
        """Clean shutdown."""
        self.hotkey_listener.stop()
        print("\nShutting down Computer-Auto...")

    def run(self, interactive_repl: bool = False) -> None:
        """Start daemon loop."""
        self.hotkey_listener.start()
        print("\n[ACTIVE] Computer-Auto is running!")
        print("  -> Press [Double-Tap Left Ctrl] OR click the HUD pill to speak.")
        print("  -> Press [Escape] at any time as the Panic Key.")
        print("  -> Press [Ctrl + C] in this console to exit.")

        if self.hud:
            try:
                self.hud.mainloop()
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
        "--interactive", "-i", action="store_true", help="Run interactive terminal command loop"
    )
    parser.add_argument(
        "--mock-stt", action="store_true", help="Use mock STT engine without downloading weights"
    )
    parser.add_argument(
        "--mock-vision", action="store_true", help="Use mock vision agent without calling Gemini API"
    )
    parser.add_argument(
        "--no-hud", action="store_true", help="Disable the floating visual HUD pill"
    )
    args = parser.parse_args()

    daemon = ComputerAutoDaemon(
        mock_stt=args.mock_stt,
        mock_vision=args.mock_vision,
        show_hud=not args.no_hud,
    )
    daemon.run(interactive_repl=args.interactive)


if __name__ == "__main__":
    main()
