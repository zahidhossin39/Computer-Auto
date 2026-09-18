"""Text-to-speech audio feedback system with SAPI5 fallback."""

import threading
from typing import Optional


class VoiceFeedback:
    """Provides low-latency spoken responses using local engines."""

    def __init__(self):
        self._sapi = None
        self._init_sapi()

    def _init_sapi(self) -> None:
        """Initialize Windows SAPI5 voice engine."""
        try:
            import win32com.client
            self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
        except Exception:
            self._sapi = None

    def speak(self, text: str, asynchronous: bool = True) -> None:
        """Speak given text string aloud."""
        if not text:
            return

        if asynchronous:
            thread = threading.Thread(target=self._speak_sync, args=(text,), daemon=True)
            thread.start()
        else:
            self._speak_sync(text)

    def _speak_sync(self, text: str) -> None:
        if self._sapi is not None:
            try:
                self._sapi.Speak(text)
            except Exception:
                pass
        else:
            # Fallback console feedback
            print(f"[Assistant Voice]: {text}")
