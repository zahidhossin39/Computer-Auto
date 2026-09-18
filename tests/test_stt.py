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
