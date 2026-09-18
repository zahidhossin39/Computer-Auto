# On-Device STT Engine and HUD Feedback

To guarantee zero speech-transcription latency and zero recurring audio API costs on a standard quad-core CPU with integrated graphics, the system runs an ultra-lightweight on-device STT engine (Moonshine / SenseVoice via ONNX runtime) consuming under 300MB RAM. Visual state feedback is delivered via a lightweight, click-through, non-focus-stealing HUD pill that indicates listening, routing, and execution states without interrupting the user's active application.
