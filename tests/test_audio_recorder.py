"""Tests for Audio Recorder."""

import numpy as np
import pytest
from src.audio.recorder import AudioRecorder


def test_audio_buffer_accumulation():
    """Verify that audio chunks accumulate in memory and are returned on stop."""
    recorder = AudioRecorder(sample_rate=16000)

    recorder.start()
    assert recorder.is_recording is True

    # Simulate 2 incoming audio chunks
    chunk1 = np.ones(1600, dtype=np.float32) * 0.5
    chunk2 = np.ones(1600, dtype=np.float32) * -0.5
    recorder.feed_audio_chunk(chunk1)
    recorder.feed_audio_chunk(chunk2)

    samples = recorder.stop()
    assert recorder.is_recording is False
    assert len(samples) == 3200
    assert np.allclose(samples[:1600], 0.5)
    assert np.allclose(samples[1600:], -0.5)


def test_empty_audio_recording():
    """Verify stopping without chunks returns an empty array."""
    recorder = AudioRecorder(sample_rate=16000)
    recorder.start()
    samples = recorder.stop()
    assert len(samples) == 0
