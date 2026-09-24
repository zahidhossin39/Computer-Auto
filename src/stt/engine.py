"""Speech recognizer: Parakeet on-device, or a cloud transcription model via OpenRouter."""

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

TRANSCRIBE_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
# Names the local model mishears; the cloud model takes them as a spelling hint
VOCAB_HINT = "Claude, Claude Code, Chrome, Discord, VS Code, Notepad, new tab, YouTube, Gmail"


class SpeechRecognizer:
    """Parakeet TDT on CPU by default; `cloud_model` (e.g. openai/gpt-4o-transcribe) sends
    audio to OpenRouter instead: ~1.3s, ~$0.0002 a command, better with names."""

    def __init__(
        self,
        model_dir: Optional[str] = "models/parakeet-tdt-0.6b-int8",
        mock_mode: bool = False,
        cloud_model: str = "",
    ):
        self.model_dir = Path(model_dir) if model_dir else None
        self.mock_mode = mock_mode
        self._recognizer = None
        self.cloud_model = cloud_model

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

    def _transcribe_cloud(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        """OpenRouter's transcription endpoint; "" on any failure so Parakeet takes over."""
        import requests
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            return ""
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
            r = requests.post(TRANSCRIBE_URL, headers={"Authorization": f"Bearer {key}"},
                              data={"model": self.cloud_model, "prompt": VOCAB_HINT},
                              files={"file": ("command.wav", buf.getvalue(), "audio/wav")}, timeout=15)
            r.raise_for_status()
            return r.json().get("text", "").strip().rstrip(".?!,:;\"'").strip().lower()
        except Exception as e:
            print(f"[STT]: cloud transcription failed ({e}), using the local model")
            return ""

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio samples (1D float32 numpy array) to lowercase text."""
        if samples is None or len(samples) == 0:
            return ""

        duration = len(samples) / sample_rate
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0

        # Matches the recorder's own speech threshold (peak 0.010): anything it
        # considered speech must reach the model, or quiet speech vanishes silently.
        if duration < 0.4 or peak < 0.010:
            print(f"[STT]: ignored {duration:.2f}s of audio (peak {peak:.3f}) - too short or too quiet")
            return ""

        if self.mock_mode:
            return "mock transcription"

        # Normalize soft audio to nominal acoustic range (0.5 peak) to aid Sherpa recognition
        max_amp = float(np.max(np.abs(samples))) if len(samples) > 0 else 0.0
        if 0.002 < max_amp < 0.25:
            samples = (samples / max_amp * 0.5).astype(np.float32)

        text = self._transcribe_cloud(samples, sample_rate) if self.cloud_model else ""
        if not text and self._recognizer is not None:
            try:
                stream = self._recognizer.create_stream()
                stream.accept_waveform(sample_rate, samples)
                self._recognizer.decode_stream(stream)
                text = stream.result.text.strip().rstrip(".?!,:;\"'").strip().lower()
            except Exception:
                text = ""
        if text:
            print(f'[STT]: "{text}" ({duration:.2f}s, peak {peak:.3f})')
        else:
            print(f"[STT]: no words recognised in {duration:.2f}s of audio (peak {peak:.3f})")
        return text
