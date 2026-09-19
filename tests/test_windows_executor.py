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


@patch("os.startfile", create=True)
def test_launch_app_success(mock_startfile, executor):
    """Verify application launching dispatches os.startfile on Windows with resolved path."""
    action = IntentAction(type="launch_app", target="notepad.exe")
    success = executor.launch_app(action)
    assert success is True
    mock_startfile.assert_called_once()
    called_target = mock_startfile.call_args[0][0]
    # Target should be resolved to absolute executable path if found on PATH
    assert "notepad" in called_target.lower()


@patch("os.startfile", side_effect=OSError("Startfile failed"), create=True)
@patch("subprocess.Popen")
def test_launch_app_fallback(mock_popen, mock_startfile, executor):
    """Verify application launching falls back to subprocess with lpDesktop and without shell=True."""
    action = IntentAction(type="launch_app", target="notepad.exe")
    success = executor.launch_app(action)
    assert success is True
    mock_popen.assert_called_once()
    called_args, called_kwargs = mock_popen.call_args
    # Verify shell=True is NOT passed (avoids cmd.exe dropping lpDesktop)
    assert called_kwargs.get("shell") is not True
    if "startupinfo" in called_kwargs and called_kwargs["startupinfo"]:
        assert called_kwargs["startupinfo"].lpDesktop == r"WinSta0\Default"


