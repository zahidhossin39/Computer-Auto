"""Speech recognizer: Parakeet on-device, or a cloud transcription model via OpenRouter."""

import io
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import threading
import time
from typing import Callable, Optional
import urllib.request
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
PARAKEET_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2"
)
PARAKEET_REQUIRED_FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
# Names the local model mishears; the cloud model takes them as a spelling hint
VOCAB_HINT = (
    "Claude, Claude Code, Chrome, Discord, VS Code, Notepad, Explorer, Terminal, "
    "PowerShell, Spotify, Slack, Teams, Settings, Calculator, new tab, close tab, "
    "close window, minimize, maximize, restore, switch to, YouTube, Gmail, GitHub, ChatGPT"
)


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

    @property
    def has_local_model(self) -> bool:
        """Whether the local Sherpa-ONNX Parakeet model is loaded."""
        return self._recognizer is not None

    @property
    def is_ready(self) -> bool:
        """Whether any transcription backend (mock, cloud, or local ONNX) is available."""
        return bool(self.mock_mode or self.cloud_model or self._recognizer is not None)

    def reload_local_model(self) -> bool:
        """Re-initialize the local Sherpa-ONNX model (e.g. after downloading weights)."""
        self._recognizer = None
        self._init_sherpa()
        return self._recognizer is not None

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
        """Transcribe speech audio via OpenRouter API with multimodal fallback."""
        import base64
        import requests
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            return ""
        model = (self.cloud_model or "google/gemini-2.5-flash").strip()
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
            wav_bytes = buf.getvalue()

            # 1. Standard audio/transcriptions endpoint (tested contract & whisper-compatible)
            try:
                r = requests.post(
                    TRANSCRIBE_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    data={"model": model, "prompt": VOCAB_HINT},
                    files={"file": ("command.wav", wav_bytes, "audio/wav")},
                    timeout=15,
                )
                r.raise_for_status()
                text = str(r.json().get("text", "")).strip().strip("\"'").rstrip(".?!,:;\"'").strip().lower()
                if text:
                    print(f'[STT CLOUD]: "{text}" ({model})')
                    return text
            except Exception as e_std:
                # If OpenRouter returns 400 (e.g. Model google/gemini-2.5-flash does not exist on transcription endpoint),
                # use chat/completions with input_audio which Gemini natively supports.
                pass

            # 2. Multimodal chat/completions with input_audio fallback (Gemini / GPT-4o)
            try:
                b64_audio = base64.b64encode(wav_bytes).decode("ascii")
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "You are an accurate, fast speech transcriber for computer desktop voice commands. "
                                        "Listen to this audio clip and transcribe the spoken words into lowercase English text. "
                                        "Spelling hints: Claude, Chrome, Discord, VS Code, Notepad, Explorer, Terminal, "
                                        "PowerShell, Spotify, Slack, Teams, Settings, Calculator, new tab, close tab, "
                                        "close window, minimize, maximize, restore, switch to, YouTube, Gmail, GitHub. "
                                        "Respond ONLY with the transcribed words. No punctuation, no markdown, no quotes. "
                                        "If the audio is silent or unintelligible noise, respond with an empty string."
                                    ),
                                },
                                {
                                    "type": "input_audio",
                                    "input_audio": {"data": b64_audio, "format": "wav"},
                                },
                            ],
                        }
                    ],
                    "temperature": 0.0,
                }
                r2 = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=15,
                )
                if r2.status_code == 200:
                    choices = r2.json().get("choices", [])
                    if choices:
                        raw = choices[0].get("message", {}).get("content", "")
                        lower = raw.strip().lower().strip("\"'").rstrip(".?!,:;\"'").strip()
                        if any(phrase in lower for phrase in ("cannot transcribe", "audio is silent", "no speech detected", "sorry, i cannot")):
                            return ""
                        if lower:
                            print(f'[STT CLOUD]: "{lower}" ({model})')
                            return lower
            except Exception:
                pass

            return ""
        except Exception as e:
            print(f"[STT CLOUD]: cloud transcription failed ({e})")
            return ""

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio samples (1D float32 numpy array) to lowercase text."""
        if samples is None or len(samples) == 0:
            return ""

        has_api_key = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
        if not self.is_ready and not has_api_key:
            print("[STT]: offline model not downloaded (and no cloud STT configured)")
            return ""

        samples = np.asarray(samples, dtype=np.float32)
        if samples.size > 0 and float(np.ptp(samples)) > 1e-6:
            samples = (samples - float(np.mean(samples))).astype(np.float32)

        duration = len(samples) / sample_rate
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0

        # Matches the recorder's silence threshold (peak 0.008): soft spoken commands
        # that triggered VAD must reach the model instead of being silently dropped.
        if duration < 0.35 or peak < 0.008:
            print(f"[STT]: ignored {duration:.2f}s of audio (peak {peak:.3f}) - too short or too quiet")
            return ""

        if self.mock_mode:
            return "mock transcription"

        # Normalize soft audio to nominal acoustic range (0.5 peak) to aid Sherpa recognition
        if 0.002 < peak < 0.25:
            samples = (samples / peak * 0.5).astype(np.float32)

        text = self._transcribe_cloud(samples, sample_rate) if self.cloud_model else ""
        if not text and self._recognizer is not None:
            try:
                stream = self._recognizer.create_stream()
                stream.accept_waveform(sample_rate, samples)
                self._recognizer.decode_stream(stream)
                text = stream.result.text.strip().rstrip(".?!,:;\"'").strip().lower()
            except Exception:
                text = ""
        if not text and not self.cloud_model and duration >= 0.35 and peak >= 0.012 and has_api_key:
            text = self._transcribe_cloud(samples, sample_rate)
        if text:
            print(f'[STT]: "{text}" ({duration:.2f}s, peak {peak:.3f})')
        else:
            print(f"[STT]: no words recognised in {duration:.2f}s of audio (peak {peak:.3f})")
        return text


def download_parakeet_model(
    model_dir: Path,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    """Download and extract the Parakeet TDT INT8 Sherpa-ONNX model files into `model_dir`."""
    target_dir = Path(model_dir)
    tmp_dir = Path(tempfile.mkdtemp(prefix="parakeet_dl_"))
    archive_path = tmp_dir / "parakeet.tar.bz2"
    staging_dir = tmp_dir / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    required = set(PARAKEET_REQUIRED_FILES)

    def _check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Model download cancelled")

    try:
        _check_cancel()
        downloaded = 0
        total_bytes = 0
        last_report = 0.0

        with urllib.request.urlopen(PARAKEET_MODEL_URL, timeout=30) as resp:
            raw_len = resp.headers.get("Content-Length") if resp.headers else None
            try:
                total_bytes = max(0, int(raw_len)) if raw_len else 0
            except (TypeError, ValueError):
                total_bytes = 0

            if progress_cb is not None:
                progress_cb(0, total_bytes, "Downloading offline speech model...")

            with open(archive_path, "wb") as out_f:
                while True:
                    _check_cancel()
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    downloaded += len(chunk)
                    now = time.monotonic()
                    if progress_cb is not None and (now - last_report >= 0.1):
                        last_report = now
                        progress_cb(downloaded, total_bytes, "Downloading offline speech model...")

        if progress_cb is not None:
            progress_cb(downloaded, total_bytes, "Extracting model files...")

        with tarfile.open(archive_path, "r:bz2") as tar:
            for member in tar.getmembers():
                _check_cancel()
                member_path = Path(member.name)
                if member.name.startswith(("/", "\\")) or ".." in member_path.parts:
                    raise ValueError(f"Unsafe tar member path: {member.name}")
                if not member.isfile():
                    continue
                fname = member_path.name
                if fname not in required:
                    continue
                src_f = tar.extractfile(member)
                if src_f is None:
                    continue
                with src_f, open(staging_dir / fname, "wb") as dst_f:
                    shutil.copyfileobj(src_f, dst_f)

        missing = [f for f in PARAKEET_REQUIRED_FILES if not (staging_dir / f).is_file()]
        if missing:
            raise FileNotFoundError(f"Missing model files in archive: {', '.join(missing)}")

        _check_cancel()
        target_dir.mkdir(parents=True, exist_ok=True)
        for fname in PARAKEET_REQUIRED_FILES:
            tmp_target = target_dir / f".{fname}.tmp"
            shutil.copy2(staging_dir / fname, tmp_target)
            os.replace(tmp_target, target_dir / fname)

        if progress_cb is not None:
            progress_cb(downloaded, total_bytes, "Offline speech model ready")

        return target_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
