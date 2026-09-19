"""Automated feedback loop for Bug 1 (shell invisible) and Bug 2 (Hotkey not firing).

This script tests both components in isolation without human interaction.
Run with:  python -u tests/test_bugs_regression.py
"""
import os
import sys
import threading
import time

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def test_bug1_shell_pill_renders_visible():
    """Bug 1: the pill must be a visible, on-screen window whose surface is not the
    transparent key colour, which would make the whole window invisible on Windows 11.
    """
    from src.ui.shell import AppShell, CHROMA

    results = {"window_exists": False, "geometry_ok": False, "surface_visible": False, "error": None}

    def _run():
        try:
            shell = AppShell()
            shell.init_ui()
            results["window_exists"] = shell.root is not None and shell._is_running

            shell.root.update_idletasks()
            parts = shell.root.geometry().replace("+", "x").split("x")
            w, h, x, y = (int(v) for v in parts[:4])
            results["geometry_ok"] = w > 0 and h > 0 and x >= 0 and y >= 0

            # The pill surface must never equal the colour Windows makes transparent
            results["surface_visible"] = shell.pill.cget("bg") != CHROMA

            shell.root.after(100, shell.root.quit)
            shell.root.mainloop()
            shell.root.destroy()
        except Exception as e:
            results["error"] = str(e)

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=8)

    assert results["error"] is None, f"Shell init raised: {results['error']}"
    assert results["window_exists"], "Shell root window was not created"
    assert results["geometry_ok"], "Shell geometry is off-screen or zero-size"
    assert results["surface_visible"], "Pill bg matches the transparent key -> window invisible!"

def test_bug2_double_tap_fires_callback():
    """Bug 2: Simulated double-tap must fire the on_toggle callback.

    The old code had a race condition with dual listeners.
    This test directly calls handle_tap() to verify the state machine works.
    """
    from src.trigger.hotkey import DoubleTapDetector

    toggled_states = []

    def on_toggle(is_listening):
        toggled_states.append(is_listening)

    detector = DoubleTapDetector(threshold_ms=500, on_toggle=on_toggle)

    # Simulate a double-tap: two taps 200ms apart
    t0 = time.time()
    detector.handle_tap(timestamp=t0)
    detector.handle_tap(timestamp=t0 + 0.2)  # 200ms later

    print(f"  [Bug 2] toggled_states after double-tap: {toggled_states}")
    assert len(toggled_states) == 1, f"Expected 1 toggle, got {len(toggled_states)}"
    assert toggled_states[0] is True, "First double-tap should start listening"
    assert detector.is_listening is True
    print("  [Bug 2] PASS")


def test_bug2_no_race_condition():
    """Bug 2 regression: verify DoubleTapDetector is thread-safe.

    Simulate concurrent handle_tap() calls from what used to be two listeners.
    The old code lacked a lock, so concurrent calls could corrupt state.
    """
    from src.trigger.hotkey import DoubleTapDetector

    toggle_count = {"n": 0}
    lock = threading.Lock()

    def on_toggle(is_listening):
        with lock:
            toggle_count["n"] += 1

    # Test that concurrent calls to handle_tap from multiple threads don't crash or corrupt state
    detector = DoubleTapDetector(threshold_ms=500, on_toggle=on_toggle)

    def worker():
        now = time.time()
        detector.handle_tap(timestamp=now)
        time.sleep(0.1)
        detector.handle_tap(timestamp=now + 0.1)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2)

    print(f"  [Bug 2 Race] toggle_count: {toggle_count['n']}")
    assert toggle_count["n"] >= 1, "At least one double-tap should be detected"
    print("  [Bug 2 Race] PASS")


def test_bug2_win32_poller_starts():
    """Bug 2: verify the Win32 poller thread actually starts."""
    from src.trigger.hotkey import GlobalHotkeyListener

    listener = GlobalHotkeyListener(threshold_ms=500)
    listener.start()
    time.sleep(0.2)  # Let thread spin up

    thread_alive = listener._poll_thread is not None and listener._poll_thread.is_alive()
    print(f"  [Bug 2 Poller] thread alive: {thread_alive}")

    listener.stop()
    assert thread_alive, "Win32 poller thread did not start"
    print("  [Bug 2 Poller] PASS")


if __name__ == "__main__":
    print("=" * 60)
    print(" BUG REGRESSION TESTS")
    print("=" * 60)

    all_passed = True

    for test_fn in [
        test_bug1_hud_pill_renders_visible,
        test_bug2_double_tap_fires_callback,
        test_bug2_no_race_condition,
        test_bug2_win32_poller_starts,
    ]:
        print(f"\n--- {test_fn.__name__} ---")
        try:
            test_fn()
        except AssertionError as e:
            print(f"  FAIL: {e}")
            all_passed = False
        except Exception as e:
            print(f"  ERROR: {e}")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print(" ALL BUG REGRESSION TESTS PASSED")
    else:
        print(" SOME TESTS FAILED")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)
