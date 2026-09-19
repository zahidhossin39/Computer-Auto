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


def test_audio_resampling_from_48k_to_16k():
    """Verify that audio recorded at 48000Hz is accurately resampled to 16000Hz on stop."""
    recorder = AudioRecorder(sample_rate=16000)
    recorder.is_recording = True
    recorder.actual_sample_rate = 48000

    # 1 second of 48000Hz audio
    raw_48k = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 48000, endpoint=False)).astype(np.float32)
    recorder.feed_audio_chunk(raw_48k)

    resampled = recorder.stop()
    assert len(resampled) == 16000
    assert resampled.dtype == np.float32


def test_multichannel_downmix():
    """Verify stereo chunks are averaged to mono float32."""
    recorder = AudioRecorder(sample_rate=16000)
    recorder.is_recording = True

    # Stereo chunk: Left channel 0.2, Right channel 0.8 -> mean 0.5
    stereo_chunk = np.zeros((160, 2), dtype=np.float32)
    stereo_chunk[:, 0] = 0.2
    stereo_chunk[:, 1] = 0.8
    recorder.feed_audio_chunk(stereo_chunk)

    samples = recorder.stop()
    assert len(samples) == 160
    assert np.allclose(samples, 0.5, atol=1e-5)


def test_silence_auto_stop_callback():
    """Verify VAD silence callback triggers when speech is followed by silence."""
    triggered = {"count": 0}

    def on_silence():
        triggered["count"] += 1

    recorder = AudioRecorder(sample_rate=16000)
    recorder.on_silence = on_silence
    recorder.is_recording = True

    # Simulate voice active chunk
    active_chunk = np.ones((500, 1), dtype=np.float32) * 0.1
    recorder._audio_callback(active_chunk, 500, None, 0)
    assert recorder._speech_detected is True

    # Trigger auto-stop directly
    recorder._trigger_auto_stop()
    import time
    time.sleep(0.05)
    assert triggered["count"] == 1
    recorder.stop()


def test_vad_soft_speech_detection():
    """Verify soft speech triggers speech detection via RMS and peak energy."""
    recorder = AudioRecorder(sample_rate=16000)
    recorder.is_recording = True

    # Soft speech chunk: peak 0.012, rms ~0.005
    soft_chunk = np.ones((1600, 1), dtype=np.float32) * 0.012
    recorder.feed_audio_chunk(soft_chunk)
    assert recorder._speech_detected is True


def test_vad_hard_timeout_prevents_infinite_hang():
    """Verify that continuous ambient noise cannot hang the recorder indefinitely."""
    triggered = {"count": 0}

    def on_silence():
        triggered["count"] += 1

    recorder = AudioRecorder(sample_rate=16000)
    recorder.on_silence = on_silence
    recorder.is_recording = True
    # Simulate recording started 8 seconds ago
    import time
    recorder._recording_start_time = time.time() - 8.0

    # Feed ambient noise chunk
    noise_chunk = np.ones((500, 1), dtype=np.float32) * 0.018
    recorder.feed_audio_chunk(noise_chunk)

    time.sleep(0.05)
    assert triggered["count"] == 1
    recorder.stop()





def test_silence_before_speech_keeps_waiting():
    """No speech yet: the recorder keeps listening and drops old silence instead of auto-stopping."""
    import time
    from unittest.mock import MagicMock
    recorder = AudioRecorder(sample_rate=16000)
    recorder.is_recording = True
    recorder.on_silence = MagicMock()
    recorder._recording_start_time = time.time() - 60  # long idle wait
    for _ in range(20):
        recorder.feed_audio_chunk(np.zeros(1600, dtype=np.float32))
    time.sleep(0.1)
    recorder.on_silence.assert_not_called()
    assert sum(len(c) for c in recorder._buffer) <= 16000 * 2  # old silence was trimmed
