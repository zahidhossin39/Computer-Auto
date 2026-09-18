"""Tests for Windows OS Executor."""

from unittest.mock import Mock, patch
import pytest
from src.config import IntentAction
from src.executor.windows import WindowsExecutor


@pytest.fixture
def executor():
    return WindowsExecutor()


@patch("src.executor.windows.WindowsExecutor._send_virtual_key")
def test_volume_actions(mock_key, executor):
    """Verify volume commands dispatch correct virtual keys."""
    executor.execute_system_action("volume_step_up")
    mock_key.assert_called_with("volumeup")

    executor.execute_system_action("volume_step_down")
    mock_key.assert_called_with("volumedown")

    executor.execute_system_action("volume_toggle_mute")
    mock_key.assert_called_with("volumemute")


@patch("src.executor.windows.WindowsExecutor._send_virtual_key")
def test_media_actions(mock_key, executor):
    """Verify media commands dispatch correct virtual keys."""
    executor.execute_system_action("media_play_pause")
    mock_key.assert_called_with("playpause")

    executor.execute_system_action("media_next")
    mock_key.assert_called_with("nexttrack")

    executor.execute_system_action("media_previous")
    mock_key.assert_called_with("prevtrack")


@patch("src.executor.windows.WindowsExecutor._hotkey")
def test_window_snap_actions(mock_hotkey, executor):
    """Verify window snap actions trigger Win+Left / Win+Right hotkeys."""
    executor.execute_system_action("window_snap_left")
    mock_hotkey.assert_called_with("win", "left")

    executor.execute_system_action("window_snap_right")
    mock_hotkey.assert_called_with("win", "right")


@patch("subprocess.Popen")
def test_launch_app_success(mock_popen, executor):
    """Verify application launching dispatches subprocess."""
    action = IntentAction(type="launch_app", target="notepad.exe")
    success = executor.launch_app(action)
    assert success is True
    mock_popen.assert_called_once()
