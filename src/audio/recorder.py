"""Non-blocking audio recording into memory buffers for speech-to-text."""

import threading
from typing import List, Optional
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None


class AudioRecorder:
    """Captures 16kHz mono audio streams and accumulates samples in memory."""

    def __init__(self, sample_rate: int = 16000, device_index: Optional[int] = None):
        self.sample_rate = sample_rate
        self.device_index = device_index
        self.is_recording = False
        self._buffer: List[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        self.last_error: Optional[str] = None

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice stream callback accumulating audio."""
        if self.is_recording:
            chunk = indata[:, 0].copy()
            with self._lock:
                self._buffer.append(chunk)

    def feed_audio_chunk(self, chunk: np.ndarray) -> None:
        """Inject an audio chunk manually (used for tests or external streams)."""
        if self.is_recording:
            with self._lock:
                self._buffer.append(chunk.astype(np.float32))

    def start(self) -> None:
        """Start capturing audio."""
        self.last_error = None
        with self._lock:
            self._buffer.clear()
            self.is_recording = True

        if sd is None:
            self.last_error = "sounddevice library not available"
            return

        if self._stream is None:
            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    device=self.device_index,
                    channels=1,
                    dtype="float32",
                    callback=self._audio_callback,
                )
                self._stream.start()
            except Exception as e:
                self.last_error = f"Failed to start device {self.device_index}: {e}"
                # If specified device fails, attempt with system default device
                if self.device_index is not None:
                    try:
                        self._stream = sd.InputStream(
                            samplerate=self.sample_rate,
                            device=None,
                            channels=1,
                            dtype="float32",
                            callback=self._audio_callback,
                        )
                        self._stream.start()
                        self.last_error = None  # Fallback succeeded
                    except Exception as e2:
                        self.last_error = f"Device {self.device_index} and default fallback failed: {e2}"

    def stop(self) -> np.ndarray:
        """Stop capturing and return concatenated float32 audio samples."""
        with self._lock:
            self.is_recording = False
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

            if not self._buffer:
                return np.empty(0, dtype=np.float32)

            return np.concatenate(self._buffer, axis=0)
