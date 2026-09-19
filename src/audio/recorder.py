"""Non-blocking audio recording into memory buffers for speech-to-text."""

import threading
import time
from typing import Callable, List, Optional
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None


class AudioRecorder:
    """Captures audio streams, handles multi-rate resampling, and accumulates 16kHz mono samples."""

    def __init__(self, sample_rate: int = 16000, device_index: Optional[int] = None):
        self.sample_rate = sample_rate
        self.device_index = device_index
        self.actual_sample_rate = sample_rate
        self.actual_channels = 1
        self.is_recording = False
        self._buffer: List[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        self.last_error: Optional[str] = None
        # Bumped on every start(); stale VAD callbacks from a prior session check it
        self._generation = 0

        # Voice Activity Detection (VAD) / Silence Auto-Stop
        self.on_silence: Optional[Callable[[], None]] = None
        self.enable_vad = True
        self._speech_detected = False
        self._speech_start_time = 0.0
        self._silence_start_time = 0.0
        self._recording_start_time = 0.0
        self.speech_threshold_rms = 0.003
        self.speech_threshold_peak = 0.010
        self.silence_threshold_rms = 0.0025
        self.silence_threshold_peak = 0.008
        self.initial_silence_timeout = 4.5
        self.post_speech_silence = 1.2
        self.max_duration = 7.5

    def _process_vad(self, chunk: np.ndarray) -> None:
        """Process chunk for voice activity and trigger silence auto-stop."""
        if not self.enable_vad or not self.is_recording:
            return


        peak = float(np.max(np.abs(chunk))) if len(chunk) > 0 else 0.0
        rms = float(np.sqrt(np.mean(chunk**2))) if len(chunk) > 0 else 0.0
        now = time.time()

        is_voice = (rms > self.speech_threshold_rms) or (peak > self.speech_threshold_peak)

        if not self._speech_detected:
            if is_voice:
                self._speech_detected = True
                self._speech_start_time = now
                self._silence_start_time = 0.0
            elif now - self._recording_start_time >= self.initial_silence_timeout:
                # Nobody spoke yet: keep waiting instead of processing silence. Keep only the
                # last ~0.5s so the onset of speech isn't clipped, and restart the clock so
                # max_duration measures the utterance, not the idle wait.
                keep = int(self.actual_sample_rate * 0.5)
                with self._lock:
                    tail = np.concatenate(self._buffer)[-keep:] if self._buffer else None
                    self._buffer = [tail] if tail is not None else []
                self._recording_start_time = now
                return
        else:
            is_active = (rms > self.silence_threshold_rms) or (peak > self.silence_threshold_peak)
            if is_active:
                self._silence_start_time = 0.0
            else:
                if self._silence_start_time == 0.0:
                    self._silence_start_time = now
                elif now - self._silence_start_time >= self.post_speech_silence:
                    self._trigger_auto_stop()
                    return

        # Hard ceiling on total recording duration to guarantee no indefinite hanging
        if now - self._recording_start_time >= self.max_duration:
            self._trigger_auto_stop()

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice stream callback accumulating audio and checking for silence."""
        if not self.is_recording:
            return

        # Multi-channel to mono downmix: average all channels to ensure any active mic is captured
        if indata.ndim > 1 and indata.shape[1] > 1:
            chunk = np.mean(indata, axis=1).astype(np.float32)
        elif indata.ndim > 1:
            chunk = indata[:, 0].copy().astype(np.float32)
        else:
            chunk = indata.copy().astype(np.float32)

        with self._lock:
            self._buffer.append(chunk)

        self._process_vad(chunk)

    def _trigger_auto_stop(self) -> None:
        """Trigger the silence callback on a separate thread to avoid deadlocking audio callback."""
        if self.on_silence and self.is_recording:
            cb = self.on_silence
            self.on_silence = None  # Prevent repeated triggers
            gen = self._generation

            def _fire():
                # Suppress stale callbacks if a new recording session started meanwhile
                if self._generation == gen:
                    cb()

            threading.Thread(target=_fire, daemon=True).start()

    def feed_audio_chunk(self, chunk: np.ndarray) -> None:
        """Inject an audio chunk manually (used for tests or external streams)."""
        if self.is_recording:
            if chunk.ndim > 1 and chunk.shape[1] > 1:
                mono = np.mean(chunk, axis=1).astype(np.float32)
            elif chunk.ndim > 1:
                mono = chunk[:, 0].copy().astype(np.float32)
            else:
                mono = chunk.astype(np.float32)
            with self._lock:
                self._buffer.append(mono)
            self._process_vad(mono)


    def start(self) -> None:
        """Start capturing audio with automatic hardware sample-rate and channel negotiation."""
        self.last_error = None
        self._speech_detected = False
        self._silence_start_time = 0.0
        self._recording_start_time = time.time()
        self._generation += 1

        with self._lock:
            self._buffer.clear()
            self.is_recording = True

        if sd is None:
            self.last_error = "sounddevice library not available"
            self.is_recording = False
            return

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # Build prioritized list of (device, sample_rate, channels) candidate configurations
        candidates = []
        if self.device_index is not None:
            try:
                info = sd.query_devices(self.device_index)
                native_sr = int(info.get("default_samplerate", 44100))
                max_ch = max(1, int(info.get("max_input_channels", 1)))
                rates = [self.sample_rate, native_sr, 44100, 48000]
                channels = [1, min(2, max_ch)]
                for r in rates:
                    for c in channels:
                        candidate = (self.device_index, r, c)
                        if candidate not in candidates:
                            candidates.append(candidate)
            except Exception as e:
                self.last_error = f"Failed to query device {self.device_index}: {e}"

        # Add fallback configurations on default device (device=None)
        fallback_rates = [self.sample_rate, 44100, 48000]
        try:
            default_info = sd.query_devices(None, "input")
            def_sr = int(default_info.get("default_samplerate", 44100))
            def_max_ch = max(1, int(default_info.get("max_input_channels", 1)))
            if def_sr not in fallback_rates:
                fallback_rates.insert(1, def_sr)
            fallback_channels = [1, min(2, def_max_ch)]
        except Exception:
            fallback_channels = [1, 2]

        for r in fallback_rates:
            for c in fallback_channels:
                candidate = (None, r, c)
                if candidate not in candidates:
                    candidates.append(candidate)

        # Attempt to open audio input stream across candidate configurations
        opened = False
        last_exc = None
        for dev, sr, ch in candidates:
            try:
                stream = sd.InputStream(
                    samplerate=sr,
                    device=dev,
                    channels=ch,
                    dtype="float32",
                    callback=self._audio_callback,
                )
                stream.start()
                self._stream = stream
                self.actual_sample_rate = sr
                self.actual_channels = ch
                self.last_error = None
                opened = True
                break
            except Exception as exc:
                last_exc = exc
                continue

        if not opened:
            self.is_recording = False
            self.last_error = (
                f"Failed to open audio input on device {self.device_index} (or default): {last_exc}"
            )

    def stop(self) -> np.ndarray:
        """Stop capturing and return concatenated float32 audio samples resampled to self.sample_rate."""
        with self._lock:
            self.is_recording = False
            stream = self._stream
            self._stream = None

        # Stop/close the stream OUTSIDE the lock: PortAudio may wait for an in-flight
        # audio callback to finish, and the callback needs _lock to append samples.
        # Holding _lock across stream.stop() can therefore deadlock.
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

        with self._lock:
            if not self._buffer:
                return np.empty(0, dtype=np.float32)

            raw = np.concatenate(self._buffer, axis=0)
            self._buffer.clear()

        # Resample to target sample_rate if stream recorded at a different hardware rate
        if self.actual_sample_rate != self.sample_rate and len(raw) > 0:
            target_length = int(round(len(raw) * self.sample_rate / self.actual_sample_rate))
            if target_length > 0:
                orig_indices = np.linspace(0, len(raw) - 1, num=len(raw))
                target_indices = np.linspace(0, len(raw) - 1, num=target_length)
                raw = np.interp(target_indices, orig_indices, raw).astype(np.float32)

        return raw
