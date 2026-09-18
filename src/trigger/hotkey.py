"""Hotkey detection and state machine for Push-to-Talk and Panic Key."""

import time
from typing import Callable, Optional
try:
    from pynput import keyboard
except ImportError:
    keyboard = None


class DoubleTapDetector:
    """State machine detecting double-taps within a millisecond threshold."""

    def __init__(
        self,
        threshold_ms: int = 400,
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

        if elapsed <= self.threshold_s:
            # Double-tap detected!
            self.is_listening = not self.is_listening
            self.last_tap_time = 0.0  # Reset tap history
            if self.on_toggle:
                self.on_toggle(self.is_listening)
            return True

        # First tap recorded
        self.last_tap_time = now
        return False

    def handle_panic(self) -> None:
        """Handle emergency abort keypress."""
        self.is_listening = False
        self.last_tap_time = 0.0
        if self.on_panic:
            self.on_panic()


class GlobalHotkeyListener:
    """Global keyboard hook using pynput to capture Left Ctrl double-tap and Escape."""

    def __init__(
        self,
        threshold_ms: int = 400,
        on_toggle: Optional[Callable[[bool], None]] = None,
        on_panic: Optional[Callable[[], None]] = None,
    ):
        self.detector = DoubleTapDetector(
            threshold_ms=threshold_ms, on_toggle=on_toggle, on_panic=on_panic
        )
        self._listener: Optional[keyboard.Listener] = None

    def _on_press(self, key) -> None:
        try:
            if key == keyboard.Key.ctrl_l:
                self.detector.handle_tap()
            elif key == keyboard.Key.esc:
                self.detector.handle_panic()
        except Exception as e:
            # Prevent unhandled exception in listener thread
            pass

    def start(self) -> None:
        """Start listening in a background daemon thread."""
        if keyboard is None:
            raise RuntimeError("pynput is not installed.")
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        """Stop listening."""
        if self._listener:
            self._listener.stop()
            self._listener = None
