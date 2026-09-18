# Computer-Auto

Voice-controlled desktop automation system for Windows 10/11 combining instant on-device intent routing with visual agentic computer use.

---

## Key Features

- **Double-Tap Left Ctrl**: Push-to-talk listening toggle. Double-tap to start speaking, double-tap again when done.
- **Panic Key (Escape)**: Emergency abort key that immediately halts any active mouse/keyboard automation.
- **Two-Tier Hybrid Architecture**:
  - **Tier 1 (Instant <300ms)**: Volume control, media controls, window snapping, window minimization/maximization, and application launching executed natively via Windows APIs without cloud latency.
  - **Tier 2 (Gemini Vision Agent)**: Unscripted commands (e.g. *"click the blue submit button"*, *"scroll down"*) route to Google Gemini Flash with live DPI-aware screen perception.
- **On-Device STT**: NVIDIA Parakeet TDT 0.6B (INT8 via Sherpa-ONNX) running offline on CPU with 2.1% WER.
- **Safety Guardrails**: Destructive actions (deletions, payments, sending emails, closing windows) trigger verbal confirmation prompts before execution.

---

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Download Offline Speech Models
Download the on-device NVIDIA Parakeet INT8 model (~400MB) with one command:
```bash
python scripts/download_models.py
```

### 3. Run the Automation Daemon
Start in background hotkey mode:
```bash
python main.py
```

Or start with the interactive text testing REPL:
```bash
python main.py --interactive
```

To test without downloading model weights or setting API keys:
```bash
python main.py --interactive --mock-stt --mock-vision
```

---

## Testing

Run the full automated test suite:
```bash
python -m pytest tests/
```
