"""Text-to-speech audio feedback system with SAPI5 fallback."""

import threading
from typing import Optional


class VoiceFeedback:
    """Provides low-latency spoken responses using local engines."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active_count = 0
        self._done_event = threading.Event()
        self._done_event.set()
        self._stop_event = threading.Event()

    @property
    def is_speaking(self) -> bool:
        """Return True while any synchronous or asynchronous speech call is active."""
        with self._lock:
            return self._active_count > 0

    def wait_until_done(self, timeout: float = 10.0) -> bool:
        """Block until active speech finishes or timeout elapses."""
        return self._done_event.wait(timeout=timeout)

    def stop(self) -> None:
        """Signal any pending/upcoming speech to abort."""
        self._stop_event.set()

    cancel = stop

    def _run_tracked(self, text: str) -> None:
        try:
            if not self._stop_event.is_set():
                self._speak_sync(text)
        finally:
            with self._lock:
                self._active_count = max(0, self._active_count - 1)
                if self._active_count == 0:
                    self._done_event.set()

    def speak(self, text: str, asynchronous: bool = True) -> None:
        """Speak given text string aloud."""
        if not text:
            return

        self._stop_event.clear()
        with self._lock:
            self._active_count += 1
            self._done_event.clear()

        if asynchronous:
            thread = threading.Thread(target=self._run_tracked, args=(text,), daemon=True)
            thread.start()
        else:
            self._run_tracked(text)

    def _speak_sync(self, text: str) -> None:
        """Synchronously speak using Windows SAPI5 with per-thread COM initialization."""
        co_initialized = False
        spoken = False
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            co_initialized = True
            sapi = win32com.client.Dispatch("SAPI.SpVoice")
            sapi.Speak(text)
            spoken = True
        except Exception:
            spoken = False
        finally:
            if co_initialized:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        if not spoken:
            # Fallback console feedback
            print(f"[Assistant Voice]: {text}")
