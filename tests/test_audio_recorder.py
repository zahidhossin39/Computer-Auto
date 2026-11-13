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

    # Simulate sustained voice active chunks (2 chunks >= 2 consecutive active chunks)
    active_chunk = np.ones((500, 1), dtype=np.float32) * 0.1
    recorder._audio_callback(active_chunk, 500, None, 0)
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


def test_vad_stops_in_a_noisy_room():
    """Background at peak 0.009 used to count as speech forever; it must read as silence."""
    import time
    fired = []
    recorder = AudioRecorder(sample_rate=16000)
    recorder.on_silence = lambda: fired.append(1)
    recorder.is_recording = True
    recorder._recording_start_time = time.time()
    noise = np.ones((1600, 1), dtype=np.float32) * 0.009
    recorder.feed_audio_chunk(noise)  # first 0.3s: the recorder learns this is the room
    recorder._recording_start_time -= 1.0
    recorder.feed_audio_chunk(noise)
    assert not recorder._speech_detected
    recorder.feed_audio_chunk(np.ones((1600, 1), dtype=np.float32) * 0.2)  # speech
    assert recorder._speech_detected
    recorder.post_speech_silence = 0.05
    recorder.feed_audio_chunk(noise)
    time.sleep(0.06)
    recorder.feed_audio_chunk(noise)
    time.sleep(0.05)
    assert fired == [1]


def test_vad_ignores_single_short_noise_spike():
    """A single brief (<60ms) mic bump followed by silence must not arm VAD."""
    import time
    recorder = AudioRecorder(sample_rate=16000)
    recorder.is_recording = True
    recorder._recording_start_time = time.time() - 1.0  # past calibration

    spike = np.ones((320, 1), dtype=np.float32) * 0.1  # 20ms
    silence = np.zeros((1600, 1), dtype=np.float32)
    recorder.feed_audio_chunk(spike)
    assert recorder._speech_detected is False
    recorder.feed_audio_chunk(silence)
    assert recorder._speech_detected is False
    assert recorder._voice_streak_chunks == 0


def test_vad_arms_on_two_consecutive_short_chunks():
    """Two consecutive short active chunks arm VAD."""
    import time
    recorder = AudioRecorder(sample_rate=16000)
    recorder.is_recording = True
    recorder._recording_start_time = time.time() - 1.0

    chunk = np.ones((320, 1), dtype=np.float32) * 0.05  # 20ms each
    recorder.feed_audio_chunk(chunk)
    assert recorder._speech_detected is False
    recorder.feed_audio_chunk(chunk)
    assert recorder._speech_detected is True


def test_on_level_callback_throttled_and_normalized():
    """on_level emits normalized 0.0..1.0 values throttled at ~15-20 Hz."""
    import time
    levels = []
    recorder = AudioRecorder(sample_rate=16000)
    recorder.on_level = levels.append
    recorder.is_recording = True

    recorder.feed_audio_chunk(np.ones((400, 1), dtype=np.float32) * 0.5)
    recorder.feed_audio_chunk(np.ones((400, 1), dtype=np.float32) * 0.5)  # throttled
    assert len(levels) == 1
    assert 0.0 <= levels[0] <= 1.0

    time.sleep(0.06)
    recorder.feed_audio_chunk(np.zeros((400, 1), dtype=np.float32))
    assert len(levels) == 2
    assert levels[1] == 0.0


def test_vad_adaptive_post_speech_silence_ignores_low_room_noise():
    """After normal speech (peak 0.35), low room noise (peak 0.02) must count as silence, not keep recording until 7.5s timeout."""
    import time
    fired = []
    recorder = AudioRecorder(sample_rate=16000)
    recorder.on_silence = lambda: fired.append(1)
    recorder.is_recording = True
    recorder._recording_start_time = time.time() - 1.0
    recorder.post_speech_silence = 0.05

    speech = np.ones((1600, 1), dtype=np.float32) * 0.35
    recorder.feed_audio_chunk(speech)
    assert recorder._speech_detected is True

    low_room_noise = np.ones((1600, 1), dtype=np.float32) * 0.02
    recorder.feed_audio_chunk(low_room_noise)
    assert recorder._silence_start_time is not None
    time.sleep(0.06)
    recorder.feed_audio_chunk(low_room_noise)
    time.sleep(0.05)
    assert fired == [1]


def test_vad_detects_immediate_speech_during_calibration_window():
    """Speaking immediately after mic re-arm (<0.3s) must detect voice instead of calibrating speech as noise."""
    import time
    recorder = AudioRecorder(sample_rate=16000)
    recorder.is_recording = True
    recorder._recording_start_time = time.time()

    immediate_speech = np.ones((1600, 1), dtype=np.float32) * 0.035
    recorder.feed_audio_chunk(immediate_speech)
    assert recorder._speech_detected is True
    assert recorder._noise is None


