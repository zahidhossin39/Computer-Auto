# Computer-Auto v2.2

Voice-controlled desktop automation for Windows 10/11 combining a native **Rust + Tauri v2** desktop shell, an expressive **Material Design 3 (M3)** UI with an interactive **Three.js 3D Robotic Mascot ("Nova")**, instant on-device command routing, and multimodal visual computer use.

---

## Key Features

- **Material Design 3 (M3) Interface**: Expressive Material 3 surface hierarchy, color tokens, segmented pill controls, elevated cards, and state chips designed with `@ui-ux-pro-max` and `@impeccable` guidelines (zero emoji-as-icon anti-patterns, full Lucide SVG icons).
- **Native Rust + Tauri v2 Desktop Shell**: Runs with zero console/terminal window (`IMAGE_SUBSYSTEM_WINDOWS_GUI`), ships as a Windows NSIS Setup Installer (`Computer-Auto-Setup.exe`) and standalone binary (`Computer-Auto.exe`), with native system tray integration and global controls.
- **3D Robotic Mascot ("Nova") & Command Studio**: Built with **React 18, Tailwind CSS, and Three.js**, featuring:
  - Real-time 3D mascot state animations (Ready, Listening, Thinking, Working, Confirming)
  - Live 32-bar Material 3 audio spectrum visualizer
  - Spotlight command bar for instant typed or voice execution
  - Searchable **Commands** library backed by `intents.yaml` with category filter chips
  - Inline **Guardrail** Confirm/Cancel approval cards
  - **1-click offline Parakeet STT model downloader** in Settings
  - Built-in **GitHub Releases self-updater** (`src/updater.py`)
- **Robust Windows Automation & Window Targeting**: Automatic interactive desktop attachment (`OpenInputDesktop` / `WinSta0`), generic window category resolution ("browser" -> Chrome/Edge/Firefox, "terminal" -> WindowsTerminal/cmd/powershell, "editor" -> Notepad/VS Code), focused in-window typing ("in notepad type <text>", "type in discord <text>"), phonetic window resolution (e.g. "not pet" / "not bad" -> Notepad, "dis cord" -> Discord, "cloud" -> Claude, "minima's" -> minimize), and dedicated address bar / search navigation.
- **Dual-Engine Speech-to-Text**: Offline **NVIDIA Parakeet TDT 0.6B (INT8)** via `sherpa-onnx` (~0.5s CPU inference), paired with automatic multimodal acoustic fallback (`google/gemini-2.5-flash` with audio payload) for zero-drop voice execution even on soft speech.
- **Double-Tap Left Ctrl & Continuous Mode**: Double-tap `Left Ctrl` to start speaking and double-tap again to execute, or toggle continuous listening from the HUD.
- **Panic Key (`Esc`)**: Instant emergency abort that cancels any active mouse, keyboard, or Vision Agent execution.
- **Hybrid Architecture (Rust + Python + OpenRouter + Sherpa-ONNX)**:
  - **Rust + Tauri v2 (`src-tauri/`)** manages the native window, system tray, and JSON-RPC bridge to **`src/bridge.py`**.
  - **Tier 1 (<300ms, Offline)**: Deterministic intents (`intents.yaml`) plus **TypeSafe Jev** fuzzy matching and click-racing execute volume, media, window snapping, app launching, web search, and dictation via native Windows APIs.
  - **Tier 2 (Multimodal Vision Agent)**: Unscripted GUI tasks route to **OpenRouter** (`google/gemini-2.5-flash` default) or any **custom OpenAI-compatible local endpoint** (Ollama, LM Studio, vLLM) with DPI-aware multi-monitor capture and Windows UI Automation (UIA) Set-of-Marks.
  - **On-Device Speech-to-Text**: Offline **NVIDIA Parakeet TDT 0.6B (INT8)** via `sherpa-onnx` (~0.5s CPU inference), with automatic cloud fallback (`google/gemini-2.5-flash`) when configured.
- **Local Voice Feedback**: Zero-dependency **Windows SAPI5** (`SAPI.SpVoice`) spoken confirmations and status readouts.
- **Safety Guardrails**: Destructive actions (deletions, closing windows, sending emails, payments) require spoken (*"yes"*, *"go ahead"*, *"cancel"*) or inline UI confirmation before running.

---

## Quick Start

### Option A: Windows Setup Installer (Recommended)

1. Download **`Computer-Auto-Setup.exe`** (or standalone **`Computer-Auto.exe`**) from [Releases](https://github.com/zahidhossin39/Computer-Auto/releases).
2. Run the installer and launch **Computer-Auto** (zero terminal window, no Python installation required).
3. Open **Settings -> Voice & Routing**:
   - Click **Download Model** for **1-click offline voice recognition** (~400 MB Parakeet INT8) — or use Cloud STT.
   - Select your microphone from the audio device dropdown.
4. Enter your OpenRouter API key in **Settings** (or point **Vision API Base** to a local OpenAI-compatible server like `http://localhost:11434/v1`) and click **Save Settings**.

### Option B: Running from Source

1. **Install Python & Frontend dependencies** (Python 3.10+, Node.js 18+, Rust toolchain on Windows 10/11):
   ```powershell
   pip install -r requirements.txt
   npm --prefix ui install
   ```
2. **Download the offline Parakeet STT model** (~400 MB):
   ```powershell
   python scripts/download_models.py
   ```
3. **Run Computer-Auto**:
   - Launch the Tauri v2 desktop app in dev mode:
     ```powershell
     npx --prefix ui tauri dev
     ```
   - Or run the Python backend / interactive text REPL / diagnostics directly:
     ```powershell
     python main.py --interactive
     python diagnostic.py --check-only
     ```
   - To test without model weights or an API key:
     ```powershell
     python main.py --interactive --mock-stt --mock-vision
     ```

---

## Privacy & API Key Handling

- **Local by default**: Tier 1 intents, hotkey detection, Windows SAPI5 TTS, and Parakeet STT all run 100% locally on your machine.
- **Screenshots**: Screen captures are only sent to your configured Vision endpoint when a command falls through to Tier 2. Point **Vision API Base** in Settings to a local server (e.g., `http://localhost:11434/v1`) for a completely offline setup.
- **Credentials**: API keys are stored locally in `settings.json` (or `.env`) and `%APPDATA%\Computer-Auto\settings.json`. Secret files, `logs/`, and `models/` are excluded by `.gitignore` and are never included in release artifacts.

---

## Troubleshooting

- **Microphone not picking up voice / "too short or too quiet"**: Open **Settings** and select your active microphone from the audio device dropdown, then click **Save Settings**.
- **Parakeet STT model not found**: Open **Settings -> Voice & Routing** and click **Download Model** (or run `python scripts/download_models.py`) to install `models/parakeet-tdt-0.6b-int8/` (`encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`, `tokens.txt`).
- **Vision commands failing (401 / 429)**: Verify your `OPENROUTER_API_KEY` in Settings (or `.env`), or switch to `google/gemini-2.5-flash` / a local OpenAI-compatible endpoint.
- **Runaway automation**: Press **`Esc`** at any time to trigger the Panic Key and abort immediately.
- **Quick system health check**: Run `python -u diagnostic.py --check-only` to verify hotkeys, audio input devices, ONNX models, API key, screen capture, and SAPI5 TTS.

---

## Testing & Building a Windows Release

Run the automated test suite:
```powershell
python -m pytest tests/ -v
```

Build the React + Three.js frontend, Rust + Tauri v2 binary, and NSIS Windows Setup Installer (`release_dist/Computer-Auto-Setup.exe` & `release_dist/Computer-Auto.exe`):
```powershell
python packaging/build_release.py
```
