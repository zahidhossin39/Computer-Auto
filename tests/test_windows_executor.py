"""Tests for Windows OS Executor."""

import os
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
@patch("src.executor.windows._shell_launch", return_value=False)
def test_launch_app_success(_shell, mock_startfile, executor):
    """Verify application launching dispatches os.startfile on Windows with resolved path."""
    action = IntentAction(type="launch_app", target="notepad.exe")
    success = executor.launch_app(action)
    assert success is True
    mock_startfile.assert_called_once()
    called_target = mock_startfile.call_args[0][0]
    # Target should be resolved to absolute executable path if found on PATH
    assert "notepad" in called_target.lower()


@patch("src.executor.windows._shell_launch", return_value=False)
@patch("os.startfile", side_effect=OSError("Startfile failed"), create=True)
@patch("subprocess.Popen")
def test_launch_app_fallback(mock_popen, mock_startfile, _shell, executor):
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




@patch("os.startfile", create=True)
@patch("src.executor.windows._shell_launch", return_value=True)
def test_launch_app_prefers_explorer_shell(mock_shell, mock_startfile, executor):
    """Existing executables launch via explorer (escapes IDE sandbox); unresolvable ones skip it."""
    assert executor.launch_app(IntentAction(type="launch_app", target="notepad.exe")) is True
    assert "notepad" in mock_shell.call_args[0][0].lower()
    mock_startfile.assert_not_called()
    mock_shell.reset_mock()
    executor.launch_app(IntentAction(type="launch_app", target="no_such_app_xyz.exe"))
    mock_shell.assert_not_called()
    mock_startfile.assert_called_once()


def test_get_active_window_skips_own_control_center(executor):
    """When foreground window is ours, the next foreign window in z-order is returned."""
    own_hwnd, other_hwnd = 100, 200
    pid = os.getpid()

    mock_gui = Mock()
    mock_gui.GetForegroundWindow.return_value = own_hwnd
    mock_gui.GetWindow.return_value = other_hwnd
    mock_gui.IsWindowVisible.return_value = True
    mock_gui.GetWindowText.return_value = "Some Other App"
    mock_gui.IsIconic.return_value = False

    mock_process = Mock()
    mock_process.GetWindowThreadProcessId.side_effect = (
        lambda hwnd: (0, pid) if hwnd == own_hwnd else (0, pid + 1)
    )

    mock_con = Mock()
    mock_con.GW_HWNDNEXT = 2

    with (
        patch("src.executor.windows.win32gui", mock_gui),
        patch("src.executor.windows.win32process", mock_process),
        patch("src.executor.windows.win32con", mock_con),
    ):
        assert executor._get_active_window() == other_hwnd
    mock_gui.GetWindow.assert_called_with(own_hwnd, mock_con.GW_HWNDNEXT)


@patch("src.executor.windows.WindowsExecutor._send_vk_code")
def test_key_enter_action(mock_vk, executor):
    """Verify key_enter sends VK_RETURN and reports success."""
    success = executor.execute_system_action("key_enter")
    mock_vk.assert_called_with(0x0D)
    assert success is True


def test_close_targets_other_window_not_our_own(executor):
    """window_close must never Alt+F4 our own Control Center: it closed the app once."""
    mock_gui = Mock()
    with patch("src.executor.windows.win32gui", mock_gui), \
         patch("src.executor.windows.win32con", Mock(WM_CLOSE=16)), \
         patch.object(executor, "_get_active_window", return_value=4242), \
         patch.object(executor, "_hotkey") as mock_hotkey:
        assert executor.execute_system_action("window_close_active") is True
    mock_gui.PostMessage.assert_called_once_with(4242, 16, 0, 0)
    mock_hotkey.assert_not_called()
