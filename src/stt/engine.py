"""Sherpa-ONNX offline speech recognizer using NVIDIA Parakeet TDT."""

from pathlib import Path
from typing import Optional
import numpy as np

try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None


class SpeechRecognizer:
    """Offline ASR engine running NVIDIA Parakeet TDT on CPU via Sherpa-ONNX."""

    def __init__(
        self,
        model_dir: Optional[str] = "models/parakeet-tdt-0.6b-int8",
        mock_mode: bool = False,
    ):
        self.model_dir = Path(model_dir) if model_dir else None
        self.mock_mode = mock_mode
        self._recognizer = None

        if not self.mock_mode:
            self._init_sherpa()

    def _init_sherpa(self) -> None:
        """Initialize Sherpa-ONNX recognizer if model files exist."""
        if sherpa_onnx is None or self.model_dir is None:
            return

        encoder = self.model_dir / "encoder.int8.onnx"
        decoder = self.model_dir / "decoder.int8.onnx"
        joiner = self.model_dir / "joiner.int8.onnx"
        tokens = self.model_dir / "tokens.txt"

        if not (encoder.exists() and decoder.exists() and joiner.exists() and tokens.exists()):
            # Models not yet downloaded
            return

        try:
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(encoder),
                decoder=str(decoder),
                joiner=str(joiner),
                tokens=str(tokens),
                num_threads=4,
                sample_rate=16000,
                feature_dim=80,
                decoding_method="greedy_search",
                provider="cpu",
            )
        except Exception:
            self._recognizer = None

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio samples (1D float32 numpy array) to lowercase text."""
        if samples is None or len(samples) == 0:
            return ""

        if self.mock_mode:
            return "mock transcription"

        if self._recognizer is None:
            return ""

        try:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            self._recognizer.decode_stream(stream)
            return stream.result.text.strip().lower()
        except Exception:
            return ""
