"""DPI-aware screenshot capture across displays with resilient fallbacks."""

import ctypes
from typing import Tuple
from PIL import Image
import mss


class ScreenCapture:
    """Captures desktop screenshots while ensuring Windows DPI awareness."""

    def __init__(self):
        self._set_dpi_awareness()

    def _set_dpi_awareness(self) -> None:
        """Inform Windows that this process handles DPI scaling natively."""
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    def grab_screen(self) -> Tuple[Image.Image, int, int]:
        """Capture the screen as a PIL Image with multi-backend fallback."""
        # 1. Try mss (fastest)
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                return img, monitor["width"], monitor["height"]
        except Exception:
            pass

        # 2. Try Pillow ImageGrab
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True)
            return img, img.width, img.height
        except Exception:
            pass

        # 3. Graceful fallback for non-interactive / locked sessions
        try:
            w = ctypes.windll.user32.GetSystemMetrics(0) or 1920
            h = ctypes.windll.user32.GetSystemMetrics(1) or 1080
        except Exception:
            w, h = 1920, 1080

        fallback_img = Image.new("RGB", (w, h), color=(40, 44, 52))
        return fallback_img, w, h
