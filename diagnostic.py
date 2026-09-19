"""Quick diagnostic: tests that the HUD pill appears and hotkey detects double-tap.
Run with:  python -u diagnostic.py
Then:
1. You should see a dark floating pill at the top-center of your screen.
2. Double-tap Left Ctrl — the console should print "DOUBLE TAP DETECTED".
3. Press Escape to exit.
"""
import sys
import threading
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.ui.hud import FloatingHUD
from src.trigger.hotkey import GlobalHotkeyListener


def on_toggle(is_listening):
    state_str = "LISTENING" if is_listening else "STOPPED"
    print(f"\n*** DOUBLE TAP DETECTED! State -> {state_str} ***\n")
    if hud:
        if is_listening:
            hud.update_state("listening", "Listening...", "Speak now!")
        else:
            hud.update_state("ready", "Ready", "Double-tap Ctrl to speak")


def on_panic():
    print("\n*** PANIC (Escape) pressed — exiting ***\n")
    listener.stop()
    if hud and hud.root:
        hud.root.after(0, hud._handle_close)


hud = FloatingHUD()
listener = GlobalHotkeyListener(
    threshold_ms=500,
    on_toggle=on_toggle,
    on_panic=on_panic,
)

if __name__ == "__main__":
    print("=" * 50)
    print(" DIAGNOSTIC: HUD Pill + Hotkey Test")
    print("=" * 50)
    print()
    print("1. A dark floating pill should appear at the top of your screen.")
    print("2. Double-tap Left Ctrl -> should print DOUBLE TAP DETECTED.")
    print("3. Press Escape to exit.")
    print()

    # Start hotkey listener
    listener.start()
    print("[OK] Hotkey listener started")

    # Init and run HUD on main thread
    hud.init_ui()
    print("[OK] HUD pill initialized — check the top-center of your screen!")
    print()

    try:
        hud.mainloop()
    except KeyboardInterrupt:
        pass

    listener.stop()
    print("Diagnostic complete.")
