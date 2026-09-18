"""Computer-Auto: Voice-controlled desktop automation daemon."""

import argparse
import sys
import time
import winsound

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


class ComputerAutoDaemon:
    """Central daemon tying hotkeys, speech, routing, and execution together."""

    def __init__(self, mock_stt: bool = False, mock_vision: bool = False):
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

    def play_sound(self, frequency: int, duration_ms: int = 80) -> None:
        """Play feedback audio chime."""
        try:
            winsound.Beep(frequency, duration_ms)
        except Exception:
            pass

    def on_listening_toggle(self, is_listening: bool) -> None:
        """Invoked when user double-taps Left Ctrl."""
        if is_listening:
            self.play_sound(880, 100)  # High chime
            print("\n[LISTENING] Speak your command... (Double-tap Left Ctrl again to finish)")
            self.recorder.start()
        else:
            self.play_sound(550, 100)  # Low chime
            print("[PROCESSING] Transcribing speech utterance...")
            samples = self.recorder.stop()

            if len(samples) == 0:
                print("[WARNING] No audio captured.")
                return

            text = self.recognizer.transcribe(samples)
            if not text:
                print("[NOTE] On-device Parakeet model weights not yet downloaded in 'models/'.")
                print("       Run the command via text or download Parakeet model.")
                return

            self.handle_command(text)

    def on_panic_key(self) -> None:
        """Invoked when user presses Escape."""
        print("\n[PANIC] Emergency stop triggered! Stopping all actions.")
        self.recorder.stop()
        self._is_executing = False
        self.play_sound(400, 200)

    def handle_command(self, utterance: str) -> None:
        """Process transcribed speech or typed command."""
        print(f"[UTTERANCE]: \"{utterance}\"")

        route = self.router.route(utterance)

        # 1. Tier 1: Deterministic System Intent
        if not route.is_vision and route.intent is not None:
            intent = route.intent
            print(f"[TIER 1 ROUTER]: Matched intent '{intent.name}' ({intent.category})")

            # Check Guardrails
            if self.guardrail.requires_confirmation(utterance, intent.is_destructive):
                warning = self.guardrail.format_confirmation_prompt(utterance)
                print(f"[GUARDRAIL]: {warning}")
                self.tts.speak(warning)
                return

            # Execute action
            if intent.action.type == "system_action" and intent.action.command:
                self.executor.execute_system_action(intent.action.command)
                print(f"[EXECUTED]: Action '{intent.action.command}' dispatched.")
            elif intent.action.type == "launch_app":
                success = self.executor.launch_app(intent.action)
                if success:
                    print(f"[EXECUTED]: Launched '{intent.action.target}'.")
                else:
                    print(f"[ERROR]: Could not launch '{intent.action.target}'.")

        # 2. Tier 2: Unscripted Visual Navigation via Gemini Flash
        else:
            print("[TIER 2 VISION]: Unscripted command -> routing to Gemini Flash...")
            img, w, h = self.capture.grab_screen()
            print(f"[SCREEN CAPTURE]: Screen dimensions {w}x{h}")

            action = self.vision.plan_action(utterance, img)
            print(f"[AGENT PLAN]: Action='{action.action}', Target=({action.x}, {action.y}) | {action.explanation}")

            # Check Guardrail for planned visual action
            if self.guardrail.requires_confirmation(action.explanation):
                warning = self.guardrail.format_confirmation_prompt(action.explanation)
                print(f"[GUARDRAIL]: {warning}")
                self.tts.speak(warning)
                return

            success = self.vision.execute_action(action)
            if success:
                print("[EXECUTED]: Visual action completed.")
            else:
                print("[WARNING]: Visual action could not be executed.")

    def run(self, interactive_repl: bool = False) -> None:
        """Start daemon loop."""
        self.hotkey_listener.start()
        print("\n[ACTIVE] Computer-Auto is running!")
        print("  -> Press [Double-Tap Left Ctrl] to start/stop talking.")
        print("  -> Press [Escape] at any time as the Panic Key.")
        print("  -> Press [Ctrl + C] in this console to exit.")

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

        print("\nShutting down Computer-Auto...")
        self.hotkey_listener.stop()


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
    args = parser.parse_args()

    daemon = ComputerAutoDaemon(mock_stt=args.mock_stt, mock_vision=args.mock_vision)
    daemon.run(interactive_repl=args.interactive)


if __name__ == "__main__":
    main()
