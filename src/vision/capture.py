"""DPI-aware screenshot capture across displays with resilient fallbacks."""

import ctypes
from typing import Dict, List, Optional, Tuple
from PIL import Image
import mss


class ScreenCapture:
    """Captures desktop screenshots while ensuring Windows DPI awareness."""

    def __init__(self):
        self._set_dpi_awareness()
        self.last_origin: Tuple[int, int] = (0, 0)

    def _set_dpi_awareness(self) -> None:
        """Inform Windows that this process handles DPI scaling natively."""
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    @staticmethod
    def _select_monitor(monitors: List[Dict[str, int]], hwnd: int) -> Dict[str, int]:
        """Pick the monitor containing hwnd, or virtual screen if spanning monitors."""
        default = monitors[1] if len(monitors) > 1 else monitors[0]
        if not hwnd or len(monitors) <= 1:
            return default
        try:
            import win32gui
            wl, wt, wr, wb = win32gui.GetWindowRect(hwnd)
        except Exception:
            return default

        if wr <= wl or wb <= wt:
            return default

        win_area = (wr - wl) * (wb - wt)
        hits: List[Tuple[int, Dict[str, int]]] = []
        for m in monitors[1:]:
            ml, mt = m["left"], m["top"]
            mr, mb = ml + m["width"], mt + m["height"]
            iw = min(wr, mr) - max(wl, ml)
            ih = min(wb, mb) - max(wt, mt)
            if iw > 0 and ih > 0:
                hits.append((iw * ih, m))

        if not hits:
            return default
        if len(hits) == 1:
            return hits[0][1]

        # Ignore tiny invisible-border overlaps (~7-8px DWM shadow) on adjacent monitors.
        best_area, best_mon = max(hits, key=lambda item: item[0])
        if best_area >= 0.9 * win_area:
            return best_mon
        return monitors[0]

    def grab_screen(self, hwnd: int = 0) -> Tuple[Image.Image, int, int]:
        """Capture the screen (or monitor containing hwnd) as a PIL Image."""
        # 1. Try mss (fastest)
        try:
            with mss.mss() as sct:
                monitor = self._select_monitor(sct.monitors, hwnd)
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                self.last_origin = (monitor["left"], monitor["top"])
                return img, monitor["width"], monitor["height"]
        except Exception:
            pass

        # 2. Try Pillow ImageGrab
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True)
            try:
                vx = ctypes.windll.user32.GetSystemMetrics(76)
                vy = ctypes.windll.user32.GetSystemMetrics(77)
                self.last_origin = (vx, vy)
            except Exception:
                self.last_origin = (0, 0)
            return img, img.width, img.height
        except Exception:
            pass

        # 3. Graceful fallback for non-interactive / locked sessions
        try:
            w = ctypes.windll.user32.GetSystemMetrics(0) or 1920
            h = ctypes.windll.user32.GetSystemMetrics(1) or 1080
        except Exception:
            w, h = 1920, 1080

        self.last_origin = (0, 0)
        fallback_img = Image.new("RGB", (w, h), color=(40, 44, 52))
        return fallback_img, w, h

    def grab_for_window(self, hwnd: int = 0) -> Tuple[Image.Image, int, int]:
        """Capture the monitor containing hwnd and return (img, origin_x, origin_y)."""
        img, _, _ = self.grab_screen(hwnd=hwnd)
        return img, self.last_origin[0], self.last_origin[1]
