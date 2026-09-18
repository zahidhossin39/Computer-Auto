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

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.is_recording = False
        self._buffer: List[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()

    def _audio_callback(self, indata, frames, time_info, status):
        """Internal sounddevice stream callback."""
        if self.is_recording:
            # Flatten mono input to 1D float32 array
            chunk = indata.copy().flatten().astype(np.float32)
            with self._lock:
                self._buffer.append(chunk)

    def feed_audio_chunk(self, chunk: np.ndarray) -> None:
        """Inject an audio chunk manually (used for tests or external streams)."""
        if self.is_recording:
            with self._lock:
                self._buffer.append(chunk.astype(np.float32))

    def start(self) -> None:
        """Start capturing audio."""
        with self._lock:
            self._buffer.clear()
            self.is_recording = True

        if sd is not None and self._stream is None:
            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    callback=self._audio_callback,
                )
                self._stream.start()
            except Exception as e:
                # Handle cases where audio device is unavailable
                pass

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
