# Computer-Auto v2.0

Voice-controlled desktop automation system combining a native Rust + Tauri v2 desktop shell, a React + Tailwind CSS + Three.js 3D Robotic Mascot ("Nova") UI, instant intent routing, and visual agentic computer use on Windows.

## Architecture Overview

- **Native Desktop Shell (`src-tauri/`)**: Rust + Tauri v2 GUI application (`IMAGE_SUBSYSTEM_WINDOWS_GUI`, zero terminal window) managing the main window, Windows system tray, global controls, and process lifecycle.
- **Frontend UI (`ui/`)**: React + Tailwind CSS + Three.js 3D Robotic Mascot ("Nova") with real-time state animations, live audio spectrum, Spotlight command bar, searchable Commands library, inline Guardrail approval cards, 1-click offline Parakeet model downloader, and built-in GitHub Releases self-updater.
- **Python Bridge (`src/bridge.py`)**: JSON-RPC stdio bridge connecting the Rust/Tauri shell to the Python automation runtime.
- **Intelligence & Speech**: OpenRouter (`google/gemini-2.5-flash` default) for multimodal Vision Agent & cloud STT fallback, plus offline **Sherpa-ONNX Parakeet TDT 0.6B (INT8)** for local speech-to-text.

## Language

**Utterance**:
The raw speech audio captured from the user during a listening session.
_Avoid_: Recording, voice note, sound bite

**Transcription**:
The text produced by converting an utterance into words.
_Avoid_: Speech text, decoded audio

**Command Router**:
The fast decision engine that classifies a transcription into a predefined system intent or routes it to the visual agent.
_Avoid_: Intent parser, classifier, dispatcher

**System Intent**:
A predefined, deterministic action executed directly via native OS APIs without vision or visual reasoning.
_Avoid_: Shortcut, command, macro

**Vision Agent**:
The multimodal agent (via OpenRouter `google/gemini-2.5-flash` or a local OpenAI-compatible endpoint) that perceives the desktop screen through screenshots and Windows UI Automation (UIA) Set-of-Marks to execute multi-step GUI actions.
_Avoid_: Visual LLM, bot, screen reader

**Listening Session**:
The active period between pressing the hotkey to begin capturing audio and pressing it again to finalize the utterance.
_Avoid_: Recording interval, microphone state

**Nova (3D Mascot)**:
The interactive Three.js 3D robotic mascot inside the React Command Studio that reflects live pipeline states (ready, listening, thinking, working, confirming) alongside the live audio spectrum.
_Avoid_: Avatar, character, animated icon

**On-Device STT Engine**:
The CPU-optimized local speech-to-text runtime (`sherpa-onnx` Parakeet TDT 0.6B INT8) converting speech to text without external network requests or GPU requirements.
_Avoid_: Voice transcriber, audio cloud, speech API

**Guardrail Confirmation**:
A required voice or inline UI verification prompt triggered before executing destructive or irreversible desktop actions.
_Avoid_: Safety popup, dialog prompt, permission check

**Panic Key**:
A dedicated physical keypress (Escape) that instantly terminates all active mouse, keyboard, and agent execution threads.
_Avoid_: Kill switch, abort button, cancel key

**Local Voice Feedback (SAPI5 TTS)**:
The offline Windows SAPI5 (`SAPI.SpVoice`) speech synthesizer converting system feedback and guardrail confirmations into spoken audio without external network requests.
_Avoid_: Voice generator, voice clone, cloud TTS

**App Shell**:
The native Rust + Tauri v2 desktop shell (`src-tauri/`) hosting the React + Tailwind + Three.js UI (`ui/`), system tray integration, and the `src/bridge.py` sidecar.
_Avoid_: Tkinter wrapper, Electron app, console window

**Intent Registry**:
The declarative configuration (`intents.yaml`) defining mappings between user voice patterns and deterministic actions.
_Avoid_: Command list, shortcut file, macro table
