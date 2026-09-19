"""Tests for the pill shell: the states it shows, and that it never hides itself."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.shell import AppShell, ACCENT, MIC, DONE


@pytest.fixture(scope="module")
def _shell():
    # One Tk per process: creating a second root after one is destroyed breaks Tcl.
    s = AppShell()
    s.init_ui()
    yield s
    try:
        s.root.destroy()
    except Exception:
        pass


@pytest.fixture
def shell(_shell):
    _shell.set_ghost(False)
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
