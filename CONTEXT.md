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
The multimodal agent that perceives the desktop screen through screenshots and executes multi-step GUI actions.
_Avoid_: Visual LLM, bot, screen reader

**Listening Session**:
The active period between pressing the hotkey to begin capturing audio and pressing it again to finalize the utterance.
_Avoid_: Recording interval, microphone state

**HUD Pill**:
The minimal semi-transparent floating widget that displays the current activity status (listening, routing, executing) without stealing focus.
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

**Local Neural TTS Engine**:
The CPU-optimized offline speech synthesizer converting system feedback and confirmations into spoken audio.
_Avoid_: Voice generator, voice clone, speech synthesizer

**App Shell**:
The desktop container managing system tray integration, window lifecycle, and HUD presentation.
_Avoid_: GUI wrapper, main window, electron app

**Intent Registry**:
The declarative configuration defining mappings between user voice patterns and deterministic actions.
_Avoid_: Command list, shortcut file, macro table
