# Tauri App Shell and Local Piper TTS (Superseded by ADR 0007)

*Status: Superseded by [0007-tkinter-m3-shell-and-sapi5-tts.md](0007-tkinter-m3-shell-and-sapi5-tts.md).*

Originally, the architecture proposed Tauri (Rust) as the native App Shell communicating with a Python sidecar via IPC, paired with Piper TTS for offline speech synthesis. In practice, maintaining a separate Rust/Tauri build and shipping Piper ONNX voice binaries added unnecessary packaging complexity on Windows. The implemented stack uses a pure-Python Material Design 3 Tkinter floating pill & Command Studio with native Win32 system tray integration, and Windows' built-in SAPI5 `SpVoice` COM engine for zero-dependency local TTS.
