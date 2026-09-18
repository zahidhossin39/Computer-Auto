# Tauri App Shell and Local Piper TTS

To provide a sleek, hardware-accelerated, transparent floating HUD pill with minimal memory footprint on Windows, the application uses Tauri (Rust) as the native App Shell, communicating with an internal Python automation sidecar process via local IPC. Spoken feedback and guardrail confirmations are synthesized locally using Piper TTS, achieving sub-100ms response times without internet access or recurring cloud voice fees.
