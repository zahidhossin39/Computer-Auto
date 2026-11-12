# Computer-Auto

Voice-controlled desktop automation system combining instant intent routing with visual agentic computer use on Windows.

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
The multimodal agent (via OpenRouter or a local OpenAI-compatible endpoint) that perceives the desktop screen through screenshots and Windows UI Automation (UIA) Set-of-Marks to execute multi-step GUI actions.
_Avoid_: Visual LLM, bot, screen reader

**Listening Session**:
The active period between pressing the hotkey to begin capturing audio and pressing it again to finalize the utterance.
_Avoid_: Recording interval, microphone state

**HUD Pill**:
The minimal always-on-top Material Design 3 floating widget that displays live status (listening, thinking, executing, confirming) without stealing window focus, and shrinks/fades during Vision Agent captures.
_Avoid_: Overlay, popup, status window, banner

**On-Device STT Engine**:
The CPU-optimized local speech-to-text runtime converting speech to text without external network requests or GPU requirements.
_Avoid_: Voice transcriber, audio cloud, speech API

**Guardrail Confirmation**:
A required voice verification prompt triggered before executing destructive or irreversible desktop actions.
_Avoid_: Safety popup, dialog prompt, permission check

**Panic Key**:
A dedicated physical keypress (Escape) that instantly terminates all active mouse, keyboard, and agent execution threads.
_Avoid_: Kill switch, abort button, cancel key

**Local Voice Feedback (SAPI5 TTS)**:
The offline Windows SAPI5 (`SAPI.SpVoice`) speech synthesizer converting system feedback and guardrail confirmations into spoken audio without external network requests.
_Avoid_: Voice generator, voice clone, cloud TTS

**App Shell**:
The Material Design 3 Tkinter desktop shell managing the floating HUD Pill, expandable Command Studio (Studio, Commands, Settings), and native Win32 system tray integration.
_Avoid_: GUI wrapper, main window, electron app, tauri app

**Intent Registry**:
The declarative configuration defining mappings between user voice patterns and deterministic actions.
_Avoid_: Command list, shortcut file, macro table
