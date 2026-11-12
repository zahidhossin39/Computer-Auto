"""Tests for Speech Recognizer."""

from unittest.mock import Mock, patch
import numpy as np
import pytest
from src.stt.engine import SpeechRecognizer


def test_recognizer_handles_empty_samples():
    """Verify that empty audio samples return an empty transcription."""
    recognizer = SpeechRecognizer(mock_mode=True)
    text = recognizer.transcribe(np.empty(0, dtype=np.float32))
    assert text == ""


def test_mock_transcription():
    """Verify that mock mode returns mock transcription without loading ONNX weights."""
    recognizer = SpeechRecognizer(mock_mode=True)
    fake_audio = np.ones(16000, dtype=np.float32) * 0.1
    text = recognizer.transcribe(fake_audio)
    assert isinstance(text, str)


def test_silent_short_audio_ignored():
    """Verify that silent/short audio returns "" without calling the recogniser."""
    recognizer = SpeechRecognizer(mock_mode=True)
    recognizer._recognizer = Mock()
    text = recognizer.transcribe(np.zeros(1000, dtype=np.float32))
    assert text == ""
    recognizer._recognizer.create_stream.assert_not_called()


def test_loud_audio_mock_transcription():
    """Verify that normal loud audio still returns the mock transcription."""
    recognizer = SpeechRecognizer(mock_mode=True)
    audio = np.ones(16000, dtype=np.float32) * 0.5
    assert recognizer.transcribe(audio) == "mock transcription"


@patch("src.stt.engine.SpeechRecognizer._init_sherpa")
def test_real_recognizer_dispatch(mock_init):
    """Verify that transcribe calls sherpa offline stream when initialized."""
    recognizer = SpeechRecognizer(mock_mode=False)
    mock_recognizer = Mock()
    mock_stream = Mock()
    mock_stream.result.text = "turn up the volume"
    mock_recognizer.create_stream.return_value = mock_stream

    recognizer._recognizer = mock_recognizer

    audio = np.ones(16000, dtype=np.float32) * 0.2
    result = recognizer.transcribe(audio)

    assert result == "turn up the volume"
    mock_stream.accept_waveform.assert_called_once()
    mock_recognizer.decode_stream.assert_called_once_with(mock_stream)


@patch("src.stt.engine.SpeechRecognizer._init_sherpa")
def test_dc_offset_removed_before_threshold_and_normalization(mock_init):
    """DC bias must be subtracted before peak check and 0.5-peak normalization."""
    recognizer = SpeechRecognizer(mock_mode=False)
    mock_recognizer = Mock()
    mock_stream = Mock()
    mock_stream.result.text = "open chrome"
    mock_recognizer.create_stream.return_value = mock_stream
    recognizer._recognizer = mock_recognizer

    t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
    # Strong DC bias (0.05) + tiny AC noise (0.002) -> actually too quiet after DC removal
    dc_plus_quiet = (0.05 + 0.002 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    assert recognizer.transcribe(dc_plus_quiet) == ""
    mock_recognizer.create_stream.assert_not_called()

    # DC bias (0.05) + soft speech (0.02) -> accepted, DC removed, normalized to 0.5 peak
    dc_plus_speech = (0.05 + 0.02 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    assert recognizer.transcribe(dc_plus_speech) == "open chrome"
    passed_samples = mock_stream.accept_waveform.call_args[0][1]
    assert abs(float(np.mean(passed_samples))) < 1e-4
    assert np.isclose(float(np.max(np.abs(passed_samples))), 0.5, atol=0.01)


@patch("src.stt.engine.SpeechRecognizer._init_sherpa")
def test_soft_speech_008_threshold_accepted(mock_init):
    """Soft speech with peak 0.0085 (aligned with 0.008 threshold) is accepted and normalized."""
    recognizer = SpeechRecognizer(mock_mode=False)
    mock_recognizer = Mock()
    mock_stream = Mock()
    mock_stream.result.text = "hello"
    mock_recognizer.create_stream.return_value = mock_stream
    recognizer._recognizer = mock_recognizer

    t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
    soft = (0.0085 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    assert recognizer.transcribe(soft) == "hello"
    passed_samples = mock_stream.accept_waveform.call_args[0][1]
    assert np.isclose(float(np.max(np.abs(passed_samples))), 0.5, atol=0.01)


def test_parakeet_integration_en_wav():
    """Non-mocked integration test using real Parakeet ONNX weights if present."""
    from pathlib import Path
    import wave

    model_dir = Path("models/parakeet-tdt-0.6b-int8")
    wav_path = model_dir / "test_wavs" / "en.wav"
    required = [
        model_dir / "encoder.int8.onnx",
        model_dir / "decoder.int8.onnx",
        model_dir / "joiner.int8.onnx",
        model_dir / "tokens.txt",
        wav_path,
    ]
    if not all(p.exists() for p in required):
        pytest.skip("Parakeet ONNX weights or test_wavs/en.wav not present")

    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    recognizer = SpeechRecognizer(model_dir=str(model_dir), mock_mode=False)
    if recognizer._recognizer is None:
        pytest.skip("sherpa_onnx not available")

    text = recognizer.transcribe(pcm, sample_rate=sr)
    assert isinstance(text, str) and len(text) > 0


def test_readiness_properties_and_missing_model_transcribe(tmp_path, capsys):
    """has_local_model, is_ready, reload_local_model, and missing-model transcribe log."""
    rec = SpeechRecognizer(model_dir=str(tmp_path), mock_mode=False)
    assert rec.model_dir == tmp_path
    assert rec.has_local_model is False
    assert rec.is_ready is False

    # Audio with no local model and no cloud model logs clear message and returns ""
    audio = np.ones(16000, dtype=np.float32) * 0.2
    assert rec.transcribe(audio) == ""
    captured = capsys.readouterr().out
    assert "offline model not downloaded" in captured

    # Cloud model or mock_mode marks recognizer ready even without local weights
    rec_cloud = SpeechRecognizer(model_dir=str(tmp_path), mock_mode=False, cloud_model="openai/gpt-4o-transcribe")
    assert rec_cloud.has_local_model is False
    assert rec_cloud.is_ready is True

    rec_mock = SpeechRecognizer(model_dir=None, mock_mode=True)
    assert rec_mock.is_ready is True

    # reload_local_model clears and re-runs _init_sherpa
    rec._recognizer = Mock()
    assert rec.has_local_model is True
    with patch.object(rec, "_init_sherpa") as mock_init:
        assert rec.reload_local_model() is False
        mock_init.assert_called_once()


def _make_tar_bz2_bytes(files: dict) -> bytes:
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def test_download_parakeet_model_success_and_progress(tmp_path):
    """download_parakeet_model streams archive, reports progress, and extracts the 4 required files."""
    import io
    from src.stt.engine import PARAKEET_REQUIRED_FILES, download_parakeet_model

    archive_bytes = _make_tar_bz2_bytes({
        "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/encoder.int8.onnx": b"enc",
        "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/decoder.int8.onnx": b"dec",
        "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/joiner.int8.onnx": b"joi",
        "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/tokens.txt": b"tok",
        "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/README.md": b"ignored",
    })

    class FakeResp(io.BytesIO):
        headers = {}  # Intentionally omit Content-Length to test total_bytes == 0 handling

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    progress_calls = []
    dest = tmp_path / "models" / "parakeet-tdt-0.6b-int8"
    with patch("urllib.request.urlopen", return_value=FakeResp(archive_bytes)):
        out = download_parakeet_model(
            dest,
            progress_cb=lambda dl, tot, stage: progress_calls.append((dl, tot, stage)),
        )

    assert out == dest
    for fname in PARAKEET_REQUIRED_FILES:
        assert (dest / fname).is_file()
    assert not (dest / "README.md").exists()
    assert len(progress_calls) >= 2
    assert progress_calls[-1][2] == "Offline speech model ready"


def test_download_parakeet_model_cancel_cleans_up(tmp_path):
    """Cancelling download_parakeet_model aborts cleanly and leaves no partial target files."""
    import io
    import threading
    from src.stt.engine import download_parakeet_model

    cancel = threading.Event()
    dest = tmp_path / "parakeet"

    class CancellingResp(io.BytesIO):
        headers = {"Content-Length": "1000"}

        def read(self, size=-1):
            cancel.set()
            return b"partial"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    with patch("urllib.request.urlopen", return_value=CancellingResp(b"x" * 100)):
        with pytest.raises(InterruptedError):
            download_parakeet_model(dest, cancel_event=cancel)

    assert not dest.exists()
