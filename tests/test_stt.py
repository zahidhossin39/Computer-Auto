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
