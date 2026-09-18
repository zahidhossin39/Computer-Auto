# Two-Tier Hybrid Control Architecture

To achieve sub-second response times for routine desktop actions while preserving the ability to automate arbitrary GUI applications on hardware lacking a dedicated GPU, we route all transcribed voice commands through a fast typed intent classifier (TypeSafe Jev) before falling back to a cloud-hosted multimodal Vision Agent (Claude 3.5 Sonnet). Deterministic commands (volume, media, app launching, window snapping) execute directly in under 300ms via native Windows APIs, while complex or unscripted visual workflows are handed off to the Vision Agent.
