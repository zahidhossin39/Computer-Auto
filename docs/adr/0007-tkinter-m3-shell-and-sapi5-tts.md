# Material Design 3 Tkinter Shell, Win32 Tray, and Windows SAPI5 TTS

*Supersedes [0006-tauri-shell-and-piper-tts.md](0006-tauri-shell-and-piper-tts.md).*

To keep the Windows distribution self-contained, fast to iterate, and free of a separate Rust/WebView toolchain, the desktop shell is implemented in Python using Tkinter styled with Material Design 3 tokens (Dark & Light themes), paired with native Win32 system tray integration (`pywin32` / `Shell_NotifyIconW`) and `WS_EX_NOACTIVATE` / chroma-keyed floating pill presentation. The shell provides a compact always-on-top status pill that expands into the Command Studio (History, Commands, Settings tabs) and shrinks/fades out of the way during Vision Agent screen captures.

For spoken feedback and guardrail confirmations, the system uses Windows' native SAPI5 COM engine (`SAPI.SpVoice` via `pywin32` with per-thread `CoInitialize`) rather than bundling Piper TTS binaries, providing zero-dependency, offline, low-latency speech synthesis on Windows 10/11.
