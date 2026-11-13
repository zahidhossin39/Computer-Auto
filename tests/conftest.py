"""Tests must never drive the real keyboard or mouse: a missed mock once pasted into the
user's focused window. Tests that check input patch these again on top."""

from unittest.mock import MagicMock

import pyautogui
import pytest


@pytest.fixture(autouse=True)
def _no_real_input(monkeypatch):
    for name in ("hotkey", "press", "write", "click", "doubleClick", "rightClick", "scroll",
                 "moveTo", "keyDown", "keyUp", "typewrite", "dragTo"):
        monkeypatch.setattr(pyautogui, name, MagicMock())
    monkeypatch.setattr("src.apps.open_windows", lambda: [])
