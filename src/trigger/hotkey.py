"""Hotkey detection and state machine for Push-to-Talk and Panic Key."""

import threading
import time
from typing import Callable, Optional

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

try:
    import win32api
    import win32con
except ImportError:
    win32api = None
    win32con = None


class DoubleTapDetector:
    """State machine detecting double-taps within a millisecond threshold."""

    def __init__(
        self,
        threshold_ms: int = 500,
        on_toggle: Optional[Callable[[bool], None]] = None,
        on_panic: Optional[Callable[[], None]] = None,
    ):
        self.threshold_s = threshold_ms / 1000.0
        self.on_toggle = on_toggle
        self.on_panic = on_panic
        self.last_tap_time: float = 0.0
        self.is_listening: bool = False

    def handle_tap(self, timestamp: Optional[float] = None) -> bool:
        """Handle a single keypress tap event. Returns True if state toggled."""
        now = timestamp if timestamp is not None else time.time()
        elapsed = now - self.last_tap_time

        if 0.05 < elapsed <= self.threshold_s:
            # Double-tap detected!
            self.is_listening = not self.is_listening
            self.last_tap_time = 0.0
            if self.on_toggle:
                self.on_toggle(self.is_listening)
            return True

        self.last_tap_time = now
        return False

    def handle_panic(self) -> None:
        """Handle emergency abort keypress."""
        self.is_listening = False
        self.last_tap_time = 0.0
        if self.on_panic:
            self.on_panic()


class GlobalHotkeyListener:
    """Hybrid global keyboard listener using native Windows API polling + pynput."""

    def __init__(
        self,
        threshold_ms: int = 500,
        on_toggle: Optional[Callable[[bool], None]] = None,
        on_panic: Optional[Callable[[], None]] = None,
    ):
        self.detector = DoubleTapDetector(
            threshold_ms=threshold_ms, on_toggle=on_toggle, on_panic=on_panic
        )
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._pynput_listener: Optional[keyboard.Listener] = None

    def _is_ctrl_key(self, key) -> bool:
        """Robustly detect Left Ctrl across Windows driver variations."""
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl):
            return True
        if hasattr(key, "name") and key.name in ("ctrl_l", "ctrl"):
            return True
        if hasattr(key, "vk") and key.vk in (162, 17):  # VK_LCONTROL, VK_CONTROL
            return True
        return False

    def _on_pynput_press(self, key) -> None:
        try:
            if self._is_ctrl_key(key):
                self.detector.handle_tap()
            elif key == keyboard.Key.esc:
                self.detector.handle_panic()
        except Exception:
            pass

    def _windows_poller_loop(self) -> None:
        """Background thread polling Windows GetAsyncKeyState directly."""
        ctrl_was_pressed = False
        esc_was_pressed = False

        while self._running:
            try:
                # 0xA2 is VK_LCONTROL, 0x11 is VK_CONTROL
                ctrl_state = win32api.GetAsyncKeyState(0xA2) or win32api.GetAsyncKeyState(0x11)
                ctrl_is_pressed = bool(ctrl_state & 0x8000)

                if ctrl_is_pressed and not ctrl_was_pressed:
                    self.detector.handle_tap()
                ctrl_was_pressed = ctrl_is_pressed

                # 0x1B is VK_ESCAPE
                esc_state = win32api.GetAsyncKeyState(0x1B)
                esc_is_pressed = bool(esc_state & 0x8000)

                if esc_is_pressed and not esc_was_pressed:
                    self.detector.handle_panic()
                esc_was_pressed = esc_is_pressed

            except Exception:
                pass

            time.sleep(0.015)  # 15ms poll interval = ~66Hz, zero CPU impact

    def start(self) -> None:
        """Start both pynput and Windows native polling listeners."""
        self._running = True

        # 1. Start Windows native GetAsyncKeyState poller (most reliable)
        if win32api is not None:
            self._poll_thread = threading.Thread(
                target=self._windows_poller_loop, daemon=True
            )
            self._poll_thread.start()

        # 2. Start pynput hook as well
        if keyboard is not None:
            try:
                self._pynput_listener = keyboard.Listener(
                    on_press=self._on_pynput_press
                )
                self._pynput_listener.daemon = True
                self._pynput_listener.start()
            except Exception:
                pass

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._pynput_listener:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass
            self._pynput_listener = None
