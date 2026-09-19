"""Text-to-speech audio feedback system with SAPI5 fallback."""

import threading
from typing import Optional


class VoiceFeedback:
    """Provides low-latency spoken responses using local engines."""

    def __init__(self):
        pass

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
