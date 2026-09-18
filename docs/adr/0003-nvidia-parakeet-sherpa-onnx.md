# NVIDIA Parakeet TDT 0.6B via Sherpa-ONNX

To achieve industry-leading speech recognition accuracy (2.1%–2.6% clean WER) while operating purely on CPU with under 500MB of RAM, the system deploys the INT8-quantized NVIDIA Parakeet TDT 0.6B model using the Sherpa-ONNX runtime. This bypasses heavyweight PyTorch and CUDA dependencies, running at over 50x real-time speed on the Intel quad-core processor with zero recurring transcription API costs.
