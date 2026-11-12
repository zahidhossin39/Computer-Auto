"""Tests for the Material Design 3 pill shell: states, themes, multi-monitor, audio meter, and guardrails."""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.shell import ACCENT, CHROMA, DONE, MIC, AppShell
import src.ui.shell as shell_mod


@pytest.fixture(scope="module")
def _shell():
    # One Tk per process: creating a second root after one is destroyed breaks Tcl.
    s = AppShell()
    s.init_ui()
    yield s
    try:
        s._quit()
    except Exception:
        pass


@pytest.fixture
def shell(_shell):
    _shell.on_guardrail_reply = None
    _shell.daemon = None
    _shell.set_theme("dark")
    _shell.set_ghost(False)
    _shell.update_state("ready", "Ready", "Double-tap Ctrl to talk")
    _shell._collapse()
    _shell.root.update()
    return _shell


def test_pill_shows_state_and_expands_to_panel(shell):
    """The pill names the state in plain words and opens the full panel when clicked."""
    shell.update_state("listening", "Listening...", "say your command")
    shell.root.update()
    assert shell.state_lbl.cget("text") == "Listening"
    assert shell.dot.itemcget(shell._dot_id, "fill") == MIC
    assert shell.expanded is False

    shell._expand()
    shell.root.update()
    assert shell.expanded is True
    assert shell.root.winfo_width() > 400  # panel, not pill

    shell._collapse()
    shell.root.update()
    assert shell.expanded is False


def test_ghost_never_hides_the_window(shell):
    """A vision run fades and shrinks the shell. Withdrawing it once left the app invisible."""
    shell._expand()
    shell.set_ghost(True)
    shell.root.update()
    assert shell.root.winfo_ismapped(), "the shell must stay on screen while the agent looks"
    assert float(shell.root.attributes("-alpha")) == pytest.approx(0.5)
    assert shell.expanded is False  # collapsed back to the pill, out of the way

    shell.set_ghost(False)
    shell.root.update()
    assert float(shell.root.attributes("-alpha")) == pytest.approx(1.0)
    assert shell.root.winfo_ismapped()


def test_typed_command_clears_the_box(shell):
    """The old panel appended commands together ("open notepadopen the browser")."""
    seen = []
    shell.on_run_command = seen.append
    shell._expand()
    shell.cmd_entry.insert(0, "open notepad")
    shell._run_typed()
    shell.root.update()
    assert seen == ["open notepad"]
    assert shell.cmd_entry.get() == ""


def test_theme_switch_dark_and_light(shell):
    """Switching between Dark M3 and Light M3 updates surfaces and never uses CHROMA."""
    dark_bg = shell.pill.cget("bg")
    assert dark_bg != CHROMA
    assert shell.theme.is_dark is True

    shell.set_theme("light")
    shell.root.update()
    light_bg = shell.pill.cget("bg")
    assert light_bg != dark_bg
    assert light_bg != CHROMA
    assert shell.theme.is_dark is False
    assert shell.panel.cget("bg") == shell.theme.surface_container
    assert shell.theme_chip.cget("text") == "Dark"

    shell.set_theme("dark")
    shell.root.update()
    assert shell.theme.is_dark is True
    assert shell.theme_chip.cget("text") == "Light"


def test_expand_clamps_to_virtual_screen_on_secondary_monitor(shell, monkeypatch):
    """Expanding on a left-side secondary monitor must keep the panel on that monitor."""
    monkeypatch.setattr(shell_mod, "_virtual_screen", lambda w, h: (-1920, 0, 3840, 1080))
    shell._pos = (-1500, 120)
    shell._expand()
    shell.root.update()

    assert shell.expanded is True
    assert shell._pos[0] == -1500
    assert shell._pos[1] == 120


def test_audio_level_updates_meter(shell):
    """set_audio_level updates the internal level and fills the Studio meter bar."""
    shell._expand()
    shell.root.update()
    shell.set_audio_level(0.75)
    shell.root.update()

    assert shell._audio_level == pytest.approx(0.75)
    coords = shell.level_canvas.coords(shell._level_rect)
    assert coords[2] > 0


def test_guardrail_confirm_and_cancel_buttons(shell):
    """Guardrail state shows inline Confirm/Cancel buttons in both pill and panel."""
    replies = []
    shell.daemon = SimpleNamespace(confirm_pending=lambda ok: replies.append(ok))

    shell.update_state("guardrail", "Confirm?", "Close Notepad?")
    shell.root.update()
    assert shell.pill_guardrail_frame.winfo_ismapped()

    shell.pill_confirm_btn.invoke()
    assert replies == [True]

    shell._expand()
    shell.root.update()
    assert shell.panel_guardrail_frame.winfo_ismapped()

    shell.panel_cancel_btn.invoke()
    assert replies == [True, False]

    shell.update_state("ready", "Ready", "Done")
    shell.root.update()
    assert not shell.pill_guardrail_frame.winfo_ismapped()
    assert not shell.panel_guardrail_frame.winfo_ismapped()


def test_save_settings_keeps_local_endpoint_keyless(shell, monkeypatch):
    """A non-OpenRouter local vision_api_base must not force mock_mode=True when keys are empty."""
    saved = {}
    monkeypatch.setattr(shell_mod, "save_settings", lambda vals: saved.update(vals))

    fake_daemon = SimpleNamespace(
        config=SimpleNamespace(max_vision_steps=8),
        vision=SimpleNamespace(model_name="", api_key="", api_base="", mock_mode=True),
        router=SimpleNamespace(use_jev=True),
        recognizer=SimpleNamespace(cloud_model=""),
        recorder=SimpleNamespace(device_index=None),
    )
    shell.daemon = fake_daemon
    shell._expand()
    shell.key_entry.delete(0, "end")
    shell.vkey_entry.delete(0, "end")
    shell.base_entry.delete(0, "end")
    shell.base_entry.insert(0, "http://localhost:11434/v1")
    shell._save_settings()
    shell.root.update()

    assert fake_daemon.vision.api_base == "http://localhost:11434/v1"
    assert fake_daemon.vision.mock_mode is False

    # OpenRouter with no keys still enters mock_mode
    shell.base_entry.delete(0, "end")
    shell.base_entry.insert(0, "https://openrouter.ai/api/v1")
    shell._save_settings()
    shell.root.update()
    assert fake_daemon.vision.mock_mode is True


def test_offline_model_status_missing_and_ready(shell):
    """Settings displays missing vs ready status based on recognizer.has_local_model."""
    fake_rec = SimpleNamespace(has_local_model=False)
    shell.daemon = SimpleNamespace(recognizer=fake_rec)
    shell._expand()
    shell._show_tab("Settings")
    shell.root.update()

    assert "Not downloaded" in shell.offline_model_status.cget("text")
    assert shell.offline_model_btn.cget("text") == "Download Model"

    fake_rec.has_local_model = True
    shell._refresh_offline_model_ui()
    shell.root.update()
    assert "Ready" in shell.offline_model_status.cget("text")


def test_offline_model_download_button_triggers_and_resets(shell):
    """Clicking Download Model invokes daemon.download_offline_model and resets cleanly."""
    import threading
    import time

    started = threading.Event()
    proceed = threading.Event()
    fake_rec = SimpleNamespace(has_local_model=False)

    def _fake_download(progress_cb=None):
        started.set()
        if progress_cb:
            progress_cb(50 * 1024 * 1024, 100 * 1024 * 1024, "Downloading...")
        proceed.wait(timeout=2)
        fake_rec.has_local_model = True
        return True

    shell.daemon = SimpleNamespace(
        recognizer=fake_rec,
        download_offline_model=_fake_download,
        cancel_model_download=lambda: proceed.set(),
    )
    shell._expand()
    shell._show_tab("Settings")
    shell.root.update()

    shell.offline_model_btn.invoke()
    assert started.wait(timeout=2)
    shell.root.update()
    assert shell._model_downloading is True
    assert shell.offline_model_btn.cget("text") == "Cancel"

    proceed.set()
    deadline = time.time() + 2.0
    while shell._model_downloading and time.time() < deadline:
        shell._drain_ui_queue()
        shell.root.update()
        time.sleep(0.02)

    assert shell._model_downloading is False
    assert shell.offline_model_btn.cget("text") == "Download Model"
    assert "Ready" in shell.offline_model_status.cget("text")


def test_offline_model_theme_switching_no_clipping(shell):
    """Dark and Light M3 theme switching updates offline model controls cleanly."""
    shell.daemon = SimpleNamespace(recognizer=SimpleNamespace(has_local_model=False))
    shell._expand()
    shell._show_tab("Settings")
    shell.root.update()

    for mode in ("light", "dark"):
        shell.set_theme(mode)
        shell.root.update()
        assert shell.offline_model_status.winfo_reqwidth() > 0
        assert shell.offline_model_btn.winfo_reqwidth() > 0
        assert shell.offline_model_status.cget("fg") == (
            shell.theme.success if shell._has_local_model() else shell.theme.on_surface_variant
        )
