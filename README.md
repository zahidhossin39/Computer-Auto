# Computer-Auto

Voice-controlled desktop automation for Windows 10/11 that pairs instant on-device command routing with multimodal visual computer use and a Material Design 3 floating pill UI.

---

## Key Features

- **Double-Tap Left Ctrl & Continuous Mode**: Double-tap `Left Ctrl` to start speaking and double-tap again to execute, or toggle continuous listening from the pill.
- **Panic Key (`Esc`)**: Instant emergency abort that cancels any active mouse, keyboard, or Vision Agent execution.
- **Two-Tier Hybrid Architecture**:
  - **Tier 1 (<300ms, Offline)**: Deterministic intents (`intents.yaml`) plus **TypeSafe Jev** fuzzy matching and click-racing execute volume, media, window snapping, app launching, web search, and dictation directly via native Windows APIs.
  - **Tier 2 (Multimodal Vision Agent)**: Unscripted GUI tasks (e.g. *"click the blue submit button"*, *"scroll down and open settings"*) route to **OpenRouter** (`qwen/qwen3-vl-8b-instruct` default, `google/gemini-3.1-flash-lite` fallback) or any **custom OpenAI-compatible local endpoint** (Ollama, LM Studio, vLLM) with DPI-aware multi-monitor capture and Windows UI Automation (UIA) Set-of-Marks.
- **On-Device Speech-to-Text**: Offline **NVIDIA Parakeet TDT 0.6B (INT8)** via `sherpa-onnx` (~0.5s CPU inference), with optional cloud transcription models in Settings.
- **Local Voice Feedback**: Zero-dependency **Windows SAPI5** (`SAPI.SpVoice`) spoken confirmations and status readouts.
- **Safety Guardrails**: Destructive actions (deletions, closing windows, sending emails, payments) require spoken (*"yes"*, *"go ahead"*, *"cancel"*) or clickable UI confirmation before running.

---

## Material Design 3 Pill & Command Studio

Computer-Auto runs as a lightweight, always-on-top **floating pill** that never steals window focus:

- **Compact Pill**: Shows live state (Ready, Listening, Thinking, Working, Confirming), audio level feedback, mic toggle, and a quick-expand button. During Vision Agent screenshots, the pill automatically shrinks and fades out of the way.
- **Expandable Command Studio**:
  - **History**: Live command log, typed command input (test without a mic), and inline Confirm/Cancel buttons for guardrails.
  - **Commands**: Searchable catalog of Tier 1 voice triggers from `intents.yaml`.
  - **Settings**: Configure your OpenRouter API key, Vision model or custom local endpoint URL, voice engine, microphone device, Dark/Light Material Design 3 theme, and minimize-to-tray behavior.
- **System Tray**: Native Win32 tray icon for quick show/hide, listening toggle, and clean exit.

---

## Quick Start

### Option A: Pre-Built Windows Portable Release

1. Download and extract the `Computer-Auto-Windows-Portable.zip` archive from Releases.
2. *(Optional, for offline voice recognition)* Run `python scripts/download_models.py` (or place the `parakeet-tdt-0.6b-int8` folder inside `models/` next to `Computer-Auto.exe`).
3. Launch **`Computer-Auto.exe`**.
4. Open the **Settings** tab in the Command Studio to pick your microphone and enter your OpenRouter API key (or point **Vision API Base** to a local OpenAI-compatible server).

### Option B: Running from Source

1. **Install dependencies** (Python 3.10+ on Windows 10/11):
   ```powershell
   pip install -r requirements.txt
   ```
2. **Download the offline Parakeet STT model** (~400 MB):
   ```powershell
   python scripts/download_models.py
   ```
3. **Run Computer-Auto**:
   ```powershell
   python main.py
   ```
   Or launch with the interactive text REPL / diagnostic checks:
   ```powershell
   python main.py --interactive
   python diagnostic.py --check-only
   ```
   To test without model weights or an API key:
   ```powershell
   python main.py --interactive --mock-stt --mock-vision
   ```

---

## Privacy & API Key Handling

- **Local by default**: Tier 1 intents, hotkey detection, Windows SAPI5 TTS, and Parakeet STT all run 100% locally on your machine.
- **Screenshots**: Screen captures are only sent to your configured Vision endpoint when a command falls through to Tier 2. Point **Vision API Base** in Settings to a local server (e.g., `http://localhost:11434/v1`) for a completely offline setup.
- **Credentials**: API keys are stored locally in `settings.json` (or `.env`) on your machine. Both files—along with `logs/` and `models/`—are excluded by `.gitignore` and are never included in release archives.

---

## Troubleshooting

- **Microphone not picking up voice / "too short or too quiet"**: Open **Settings** and select your active microphone from the audio device dropdown, then click **Save**.
- **Parakeet STT model not found**: Run `python scripts/download_models.py` and verify `models/parakeet-tdt-0.6b-int8/` contains `encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`, and `tokens.txt`.
- **Vision commands failing (401 / 429)**: Verify your `OPENROUTER_API_KEY` in Settings (or `.env`), or switch to a fallback model / local OpenAI-compatible endpoint.
- **Runaway automation**: Press **`Esc`** at any time to trigger the Panic Key and abort immediately.
- **Quick system health check**: Run `python -u diagnostic.py --check-only` to verify hotkeys, audio input devices, ONNX models, API key, screen capture, and SAPI5 TTS.

---

## Testing & Building a Portable Release

Run the automated test suite:
```powershell
python -m pytest tests/ -v
```

Build a clean portable Windows zip in `release_dist/` (requires PyInstaller):
```powershell
python packaging/build_release.py
```
