"""Hotkey detection and state machine for Push-to-Talk and Panic Key."""

import threading
import time
from typing import Callable, Optional

try:
    import win32api
except ImportError:
    win32api = None

# Virtual key codes
VK_LCONTROL = 0xA2
VK_CONTROL = 0x11
VK_ESCAPE = 0x1B


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
        self._lock = threading.Lock()

    def handle_tap(self, timestamp: Optional[float] = None) -> bool:
        """Handle a single keypress tap event. Returns True if state toggled."""
        now = timestamp if timestamp is not None else time.time()

        with self._lock:
            elapsed = now - self.last_tap_time

            # A session is running: one tap stops it. Waiting for a second tap made
            # stopping unreliable, and there is nothing else Ctrl should do mid-session.
            if self.is_listening:
                self.is_listening = False
                self.last_tap_time = 0.0
                toggled, new_state = True, False
            elif 0.05 < elapsed <= self.threshold_s:
                # Double-tap detected!
                self.is_listening = not self.is_listening
                self.last_tap_time = 0.0
                toggled = True
                new_state = self.is_listening
            else:
                self.last_tap_time = now
                toggled = False
                new_state = None

        # Call callback outside lock to avoid deadlocks
        if toggled and self.on_toggle:
            print(f"[HOTKEY] {'Stop tap' if not new_state else 'Double-tap'} detected! Listening={new_state}")
            self.on_toggle(new_state)

        return toggled

    def handle_panic(self) -> None:
        """Handle emergency abort keypress."""
        with self._lock:
            self.is_listening = False
            self.last_tap_time = 0.0
        if self.on_panic:
            self.on_panic()


class GlobalHotkeyListener:
    """Global keyboard listener using native Windows GetAsyncKeyState polling.

    Uses ONLY the Win32 API poller (not pynput) to avoid the duplicate-event
    race condition where both listeners fire for the same physical keypress.
    """

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

    def _windows_poller_loop(self) -> None:
        """Background thread polling Windows GetAsyncKeyState directly."""
        ctrl_was_pressed = False
        esc_was_pressed = False
        print("[HOTKEY] Win32 poller thread started (polling LCtrl + Escape)")

        while self._running:
            try:
                # Check Left Ctrl (0xA2) — use bitwise check, not Python 'or'
                lctrl_state = win32api.GetAsyncKeyState(VK_LCONTROL)
                ctrl_is_pressed = bool(lctrl_state & 0x8000)

                if ctrl_is_pressed and not ctrl_was_pressed:
                    # Key just went down (edge trigger)
                    self.detector.handle_tap()
                ctrl_was_pressed = ctrl_is_pressed

                # Check Escape (0x1B)
                esc_state = win32api.GetAsyncKeyState(VK_ESCAPE)
                esc_is_pressed = bool(esc_state & 0x8000)

                if esc_is_pressed and not esc_was_pressed:
                    self.detector.handle_panic()
                esc_was_pressed = esc_is_pressed

            except Exception as e:
                print(f"[HOTKEY] Poller error: {e}")

            time.sleep(0.015)  # ~66 Hz polling

        print("[HOTKEY] Win32 poller thread stopped")

    def _pynput_fallback_loop(self) -> None:
        """Fallback for non-Windows systems using pynput."""
        try:
            from pynput import keyboard
        except ImportError:
            print("[HOTKEY] pynput not available, no keyboard listener running")
            return

        def on_press(key):
            try:
                if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl):
                    self.detector.handle_tap()
                elif key == keyboard.Key.esc:
                    self.detector.handle_panic()
            except Exception:
                pass

        print("[HOTKEY] Using pynput fallback listener")
        with keyboard.Listener(on_press=on_press) as listener:
            while self._running:
                time.sleep(0.1)
            listener.stop()

    def start(self) -> None:
        """Start the keyboard listener."""
        self._running = True

        if win32api is not None:
            # Preferred: native Win32 polling (most reliable on Windows)
            self._poll_thread = threading.Thread(
                target=self._windows_poller_loop, daemon=True
            )
            self._poll_thread.start()
        else:
            # Fallback: pynput (for non-Windows or missing win32api)
            self._poll_thread = threading.Thread(
                target=self._pynput_fallback_loop, daemon=True
            )
            self._poll_thread.start()

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
        self._poll_thread = None
