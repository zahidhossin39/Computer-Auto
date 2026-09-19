"""System Diagnostic & Interactive Prototype for Computer-Auto.

Runs automated pre-flight checks across all subsystems and launches
the visible Desktop Control Center prototype for local testing.

Usage:
  python -u diagnostic.py         # Launches full visible Desktop App prototype
  python -u diagnostic.py --hud   # Tests the compact Floating HUD pill
"""

import os
import sys

# CRITICAL: Attach thread to user's interactive 'Default' desktop BEFORE any GUI/audio/hook imports!
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

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.is_file():
        load_dotenv(dotenv_path=env_file)
except Exception:
    pass

from main import ComputerAutoDaemon
from src.trigger.hotkey import GlobalHotkeyListener
from src.ui.shell import AppShell
from src.stt.engine import SpeechRecognizer
from src.vision.capture import ScreenCapture
from src.vision.agent import VisionAgent


def run_subsystem_checks():
    """Run non-destructive self-checks and print status table."""
    print("=" * 65)
    print("  COMPUTER-AUTO SUBSYSTEM SELF-DIAGNOSTIC")
    print("=" * 65)

    checks = []

    # 1. Hotkey Subsystem
    try:
        import win32api
        checks.append(("Win32 Hotkey Poller", "OK", "Native GetAsyncKeyState available (polling LCtrl + Esc)"))
    except ImportError:
        checks.append(("Win32 Hotkey Poller", "FALLBACK", "pynput fallback active"))

    # 2. Audio Device Subsystem
    try:
        import sounddevice as sd
        devs = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        if devs:
            checks.append(("Audio Input Devices", "OK", f"Found {len(devs)} input device(s) - default: {devs[0]['name'][:30]}"))
        else:
            checks.append(("Audio Input Devices", "WARN", "No input recording devices detected"))
    except Exception as e:
        checks.append(("Audio Input Devices", "FAIL", str(e)))

    # 3. Parakeet STT Model Files
    model_dir = os.path.join(os.path.dirname(__file__), "models", "parakeet-tdt-0.6b-int8")
    req_files = ["encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"]
    missing = [f for f in req_files if not os.path.isfile(os.path.join(model_dir, f))]
    if not missing:
        checks.append(("Parakeet STT INT8", "OK", "All 4 ONNX model weights present on disk"))
    else:
        checks.append(("Parakeet STT INT8", "WARN", f"Missing model weights: {missing}"))

    # 4. OpenRouter API Key (vision agent)
    gemini_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if gemini_key:
        checks.append(("OpenRouter API Key", "OK", f"Configured in .env (len: {len(gemini_key)})"))
    else:
        checks.append(("OpenRouter API Key", "WARN", "OPENROUTER_API_KEY not found in .env"))

    # 5. Screen Capture
    try:
        cap = ScreenCapture()
        img, w, h = cap.grab_screen()
        checks.append(("Screen Capture", "OK", f"Active display captured ({w}x{h}, mode={img.mode})"))
    except Exception as e:
        checks.append(("Screen Capture", "FAIL", str(e)))

    # 6. SAPI5 Voice Feedback
    try:
        from src.tts.piper import VoiceFeedback
        tts = VoiceFeedback()
        checks.append(("Windows Voice TTS", "OK", "SAPI5 COM SpVoice engine initialized and ready"))
    except Exception as e:
        checks.append(("Windows Voice TTS", "FAIL", str(e)))

    # Print summary
    for name, status, detail in checks:
        badge = f"[{status}]"
        print(f"  {badge:8} {name:<24} {detail}")

    print("=" * 65)
    print()


def main():
    parser = argparse.ArgumentParser(description="Computer-Auto Diagnostic & Prototype")
    parser.add_argument("--hud", action="store_true", help="Launch mini Floating HUD instead of Control Center")
    parser.add_argument("--check-only", action="store_true", help="Run automated checks without opening GUI")
    args = parser.parse_args()

    run_subsystem_checks()

    if args.check_only:
        return

    mode = "hud" if args.hud else "app"
    print(f"Launching Computer-Auto in [{mode.upper()}] mode...")
    if mode == "app":
        print("A fully visible desktop Control Center window will appear.")
        print("You can test speech, hotkeys, commands, and vision navigation inside.")
    else:
        print("A floating status pill will appear at the top-center of your screen.")

    daemon = ComputerAutoDaemon(ui_mode=mode)
    daemon.run()


if __name__ == "__main__":
    main()
