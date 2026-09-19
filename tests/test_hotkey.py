"""Tests for Hotkey State Machine."""

from unittest.mock import Mock
import pytest
from src.trigger.hotkey import DoubleTapDetector


def test_single_tap_does_not_trigger():
    """Verify that a single tap does not fire the toggle callback."""
    on_toggle = Mock()
    detector = DoubleTapDetector(threshold_ms=400, on_toggle=on_toggle)

    detector.handle_tap(timestamp=1.0)
    on_toggle.assert_not_called()
    assert detector.is_listening is False


def test_rapid_double_tap_triggers_toggle():
    """Verify that two taps within 400ms fire the toggle callback."""
    on_toggle = Mock()
    detector = DoubleTapDetector(threshold_ms=400, on_toggle=on_toggle)

    detector.handle_tap(timestamp=1.0)
    detector.handle_tap(timestamp=1.2)  # 200ms later

    assert on_toggle.call_count == 1
    # First toggle starts listening
    on_toggle.assert_called_with(True)
    assert detector.is_listening is True


def test_second_double_tap_stops_listening():
    """Verify that a subsequent double-tap stops listening."""
    on_toggle = Mock()
    detector = DoubleTapDetector(threshold_ms=400, on_toggle=on_toggle)

    # First double tap -> Start
    detector.handle_tap(timestamp=1.0)
    detector.handle_tap(timestamp=1.2)
    assert detector.is_listening is True

    # Second double tap -> Stop
    detector.handle_tap(timestamp=3.0)
    detector.handle_tap(timestamp=3.2)
    assert detector.is_listening is False
    assert on_toggle.call_count == 2
    on_toggle.assert_called_with(False)


def test_slow_taps_do_not_trigger():
    """Verify that taps separated by more than threshold do not fire."""
    on_toggle = Mock()
    detector = DoubleTapDetector(threshold_ms=400, on_toggle=on_toggle)

    detector.handle_tap(timestamp=1.0)
    detector.handle_tap(timestamp=1.6)  # 600ms later -> slow

    on_toggle.assert_not_called()
    assert detector.is_listening is False


def test_panic_key_resets_and_triggers_panic_callback():
    """Verify that panic key immediately halts listening and invokes panic callback."""
    on_toggle = Mock()
    on_panic = Mock()
    detector = DoubleTapDetector(
        threshold_ms=400, on_toggle=on_toggle, on_panic=on_panic
    )

    # Start listening
    detector.handle_tap(timestamp=1.0)
    detector.handle_tap(timestamp=1.2)
    assert detector.is_listening is True

    # Hit panic
    detector.handle_panic()
    assert detector.is_listening is False
    on_panic.assert_called_once()


def test_single_tap_stops_an_active_session():
    """Once listening, one Left Ctrl tap stops it: waiting for a second tap was unreliable."""
    from src.trigger.hotkey import DoubleTapDetector
    states = []
    d = DoubleTapDetector(threshold_ms=400, on_toggle=states.append)

    d.handle_tap(timestamp=1.00)          # first tap: nothing yet
    d.handle_tap(timestamp=1.20)          # double-tap starts the session
    assert states == [True] and d.is_listening is True

    d.handle_tap(timestamp=9.00)          # a single, late tap must stop it
    assert states == [True, False] and d.is_listening is False
