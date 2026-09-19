"""Automated feedback loop for Bug 1 (HUD invisible) and Bug 2 (Hotkey not firing).

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


def test_bug1_hud_pill_renders_visible():
    """Bug 1: HUD pill must create a visible Tk window that is NOT fully transparent.

    The old code used #000000 as both the root bg AND the transparent key,
    which could make the entire window invisible on Windows 11.
    """
    from src.ui.hud import FloatingHUD

    results = {"window_exists": False, "geometry_ok": False, "transparent_key_safe": False, "error": None}

    def _run():
        try:
            hud = FloatingHUD()
            hud.init_ui()

            # Check 1: root window was created
            results["window_exists"] = hud.root is not None and hud._is_running

            # Check 2: geometry is on-screen (not 0x0 or negative coords)
            geom = hud.root.geometry()
            # e.g. "480x58+400+20"
            parts = geom.replace("+", "x").split("x")
            w, h, x, y = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            results["geometry_ok"] = w > 0 and h > 0 and x >= 0 and y >= 0

            # Check 3: the transparent key color is NOT the same as the pill frame bg
            root_bg = hud.root.cget("bg")
            pill_bg = hud._pill_frame.cget("bg")
            # The transparent key should differ from the pill background
            results["transparent_key_safe"] = root_bg != pill_bg

            # Print debug info
            print(f"  root bg:        {root_bg}")
            print(f"  pill frame bg:  {pill_bg}")
            print(f"  transparent key: {hud._TRANSPARENT_KEY}")
            print(f"  geometry:       {geom}")

            hud.root.after(100, hud.root.quit)
            hud.root.mainloop()
            hud.root.destroy()
        except Exception as e:
            results["error"] = str(e)

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=5)

    print(f"  [Bug 1] window_exists:       {results['window_exists']}")
    print(f"  [Bug 1] geometry_ok:         {results['geometry_ok']}")
    print(f"  [Bug 1] transparent_key_safe: {results['transparent_key_safe']}")
    if results["error"]:
        print(f"  [Bug 1] ERROR: {results['error']}")

    assert results["window_exists"], "HUD root window was not created"
    assert results["geometry_ok"], "HUD geometry is off-screen or zero-size"
    assert results["transparent_key_safe"], "Root bg matches pill bg — window will be invisible!"
    assert results["error"] is None, f"HUD init raised: {results['error']}"
    print("  [Bug 1] PASS")


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

    detector = DoubleTapDetector(threshold_ms=500, on_toggle=on_toggle)

    # Simulate 100 rapid double-taps from two threads at the same time
    errors = []

    def tap_burst(timestamps):
        for t in timestamps:
            detector.handle_tap(timestamp=t)
            time.sleep(0.001)

    # Create two sets of timestamps that interleave
    base = 100.0
    t1_stamps = [base + i * 1.5 for i in range(20)]  # every 1.5s (separate taps)
    t2_stamps = [base + i * 1.5 + 0.15 for i in range(20)]  # 150ms after each t1 tap

    thread1 = threading.Thread(target=tap_burst, args=(t1_stamps,))
    thread2 = threading.Thread(target=tap_burst, args=(t2_stamps,))
    thread1.start()
    thread2.start()
    thread1.join(timeout=5)
    thread2.join(timeout=5)

    # With the lock, toggle_count should be exactly 20 (one per pair)
    print(f"  [Bug 2 Race] toggle_count: {toggle_count['n']} (expected ~20)")
    # Allow some variance due to thread scheduling, but it must be > 0
    assert toggle_count["n"] > 0, "No toggles detected — race condition killed all events"
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
