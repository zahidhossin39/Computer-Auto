"""Sherpa-ONNX offline speech recognizer with Gemini Flash fallback."""

import io
import os
from pathlib import Path
from typing import Optional
import wave
import numpy as np

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


class SpeechRecognizer:
    """Speech-to-Text engine: Parakeet TDT on CPU (primary) with Gemini Flash fallback."""

    def __init__(
        self,
        model_dir: Optional[str] = "models/parakeet-tdt-0.6b-int8",
        mock_mode: bool = False,
    ):
        self.model_dir = Path(model_dir) if model_dir else None
        self.mock_mode = mock_mode
        self._recognizer = None
        self._gemini_client = None

        if not self.mock_mode:
            self._init_sherpa()
            self._init_gemini()

    def _init_sherpa(self) -> None:
        """Initialize Sherpa-ONNX recognizer if model files exist."""
        if sherpa_onnx is None or self.model_dir is None:
            return

        encoder = self.model_dir / "encoder.int8.onnx"
        decoder = self.model_dir / "decoder.int8.onnx"
        joiner = self.model_dir / "joiner.int8.onnx"
        tokens = self.model_dir / "tokens.txt"

        if not (encoder.exists() and decoder.exists() and joiner.exists() and tokens.exists()):
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
                model_type="nemo_transducer",
                decoding_method="greedy_search",
                provider="cpu",
            )
        except Exception:
            self._recognizer = None

    def _init_gemini(self) -> None:
        """Initialize Gemini client as audio fallback if available."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key and genai is not None:
            try:
                self._gemini_client = genai.Client(api_key=api_key)
            except Exception:
                self._gemini_client = None

    def _transcribe_gemini(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        """Fallback transcription via Gemini 2.5 Flash."""
        if self._gemini_client is None:
            return ""
        try:
            int16_samples = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(int16_samples.tobytes())

            resp = self._gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=buf.getvalue(), mime_type="audio/wav"),
                    "Transcribe the spoken command in this audio exactly. Return ONLY the transcribed text in lowercase, without quotes, timestamps, or commentary. If silence or unintelligible, return nothing.",
                ],
            )
            return resp.text.strip().lower()
        except Exception:
            return ""

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio samples (1D float32 numpy array) to lowercase text."""
        if samples is None or len(samples) == 0:
            return ""

        if self.mock_mode:
            return "mock transcription"

        # 1. Primary: On-device Sherpa-ONNX
        if self._recognizer is not None:
            try:
                stream = self._recognizer.create_stream()
                stream.accept_waveform(sample_rate, samples)
                self._recognizer.decode_stream(stream)
                text = stream.result.text.strip().lower()
                if text:
                    return text
            except Exception:
                pass

        # 2. Seamless Fallback: Gemini Cloud STT
        return self._transcribe_gemini(samples, sample_rate)
