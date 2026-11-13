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


def test_run_action_minimize_maximize_restore_window(executor):
    """run_action supports minimize_window, maximize_window, restore_window and handles None win32gui."""
    mock_gui = Mock()
    mock_con = Mock(SW_MINIMIZE=6, SW_MAXIMIZE=3, SW_RESTORE=9)
    with patch("src.executor.windows.win32gui", mock_gui), patch("src.executor.windows.win32con", mock_con):
        assert executor.run_action(IntentAction(type="minimize_window", target="101")) is True
        assert executor.run_action(IntentAction(type="maximize_window", target="102")) is True
        assert executor.run_action(IntentAction(type="restore_window", target="103")) is True

    mock_gui.ShowWindow.assert_any_call(101, 6)
    mock_gui.ShowWindow.assert_any_call(102, 3)
    mock_gui.ShowWindow.assert_any_call(103, 9)

    with patch("src.executor.windows.win32gui", None):
        assert executor.run_action(IntentAction(type="minimize_window", target="101")) is False
        assert executor.run_action(IntentAction(type="maximize_window", target="102")) is False
        assert executor.run_action(IntentAction(type="restore_window", target="103")) is False


def test_run_action_open_app_and_open_url_fallbacks(executor):
    """open_app and open_url fall back when _shell_launch returns False."""
    with patch("src.executor.windows._shell_launch", return_value=False), \
         patch("os.startfile", create=True) as mock_startfile:
        assert executor.run_action(IntentAction(type="open_app", target="Claude.AppID")) is True
        assert "shell:AppsFolder\\Claude.AppID" in mock_startfile.call_args[0][0]

    with patch("src.executor.windows._shell_launch", return_value=False), \
         patch("os.startfile", side_effect=OSError("fail"), create=True), \
         patch("subprocess.Popen") as mock_popen:
        assert executor.run_action(IntentAction(type="open_app", target="Claude.AppID")) is True
        mock_popen.assert_called_once()

    with patch("src.executor.windows._shell_launch", return_value=False), \
         patch("os.startfile", side_effect=OSError("fail"), create=True), \
         patch("webbrowser.open", return_value=True) as mock_wb:
        assert executor.run_action(IntentAction(type="open_url", target="https://example.com")) is True
        mock_wb.assert_called_once_with("https://example.com")


def test_type_text_preserves_non_text_clipboard_formats():
    """type_text saves and restores non-text clipboard formats (e.g. CF_DIB) alongside text."""
    import sys
    from src.executor.windows import type_text

    CF_DIB = 8
    CF_UNICODETEXT = 13
    clip_state = {CF_UNICODETEXT: "old text", CF_DIB: b"\x28\x00\x00\x00fake_dib"}
    enum_order = [CF_UNICODETEXT, CF_DIB, 0]

    mock_clip = Mock()
    mock_clip.CF_UNICODETEXT = CF_UNICODETEXT
    mock_clip.EnumClipboardFormats.side_effect = lambda fmt: (
        enum_order[0] if fmt == 0 else enum_order[enum_order.index(fmt) + 1]
    )
    mock_clip.GetClipboardData.side_effect = lambda fmt: clip_state[fmt]
    mock_clip.EmptyClipboard.side_effect = lambda: clip_state.clear()
    mock_clip.SetClipboardText.side_effect = lambda val, fmt=CF_UNICODETEXT: clip_state.__setitem__(fmt, val)
    mock_clip.SetClipboardData.side_effect = lambda fmt, val: clip_state.__setitem__(fmt, val)

    with patch.dict(sys.modules, {"win32clipboard": mock_clip}), \
         patch("src.executor.windows.send_hotkey") as mock_hotkey, \
         patch("time.sleep"):
        type_text("hello world")

    mock_hotkey.assert_called_once_with("ctrl", "v")
    assert clip_state[CF_UNICODETEXT] == "old text"
    assert clip_state[CF_DIB] == b"\x28\x00\x00\x00fake_dib"


def test_launch_app_focuses_existing_window_instead_of_opening_duplicate(executor, monkeypatch):
    """When Chrome (or another app) is already open and no special args are passed, focus it instead of spawning a duplicate."""
    from src import apps
    monkeypatch.setattr(apps, "find_window", lambda name: (999, "Google Chrome") if "chrome" in name.lower() else None)

    with patch.object(executor, "focus_window", return_value=True) as mock_focus, \
         patch("src.executor.windows._shell_launch") as mock_shell, \
         patch("os.startfile", create=True) as mock_startfile:
        assert executor.launch_app(IntentAction(type="launch_app", target="chrome.exe")) is True
        mock_focus.assert_called_once_with(999)
        mock_shell.assert_not_called()
        mock_startfile.assert_not_called()


def test_launch_app_with_chrome_profile_args_quotes_spaces_and_bypasses_focus(executor, monkeypatch):
    """When launching a specific Chrome profile (--profile-directory=Profile 5), do not just focus any Chrome window; pass quoted args."""
    from src import apps
    monkeypatch.setattr(apps, "find_window", lambda name: (999, "Google Chrome"))

    with patch.object(executor, "focus_window") as mock_focus, \
         patch.object(executor, "_resolve_executable", return_value=r"C:\Program Files\Google\Chrome\Application\chrome.exe"), \
         patch("os.path.isfile", return_value=True), \
         patch("src.executor.windows._shell_launch", return_value=True) as mock_shell:
        action = IntentAction(
            type="launch_app",
            target="chrome.exe",
            args=["--profile-directory=Profile 5", "https://mail.google.com"],
        )
        assert executor.launch_app(action) is True
        mock_focus.assert_not_called()
        mock_shell.assert_called_once_with(
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            '"--profile-directory=Profile 5" https://mail.google.com',
        )


def test_run_action_open_app_focuses_existing_window(executor, monkeypatch):
    """run_action('open_app') focuses an already-open window when found."""
    from src import apps
    monkeypatch.setattr(apps, "find_window", lambda name: (777, "Discord") if "discord" in name.lower() else None)

    with patch.object(executor, "focus_window", return_value=True) as mock_focus, \
         patch("src.executor.windows._shell_launch") as mock_shell:
        assert executor.run_action(IntentAction(type="open_app", target="com.squirrel.Discord.Discord")) is True
        mock_focus.assert_called_once_with(777)
        mock_shell.assert_not_called()


def test_focus_window_succeeds_even_when_attach_thread_input_denied(executor):
    """When foreground window is elevated and AttachThreadInput raises Access is denied,
    focus_window must still proceed to BringWindowToTop/SetForegroundWindow and return True."""
    import sys

    mock_gui = Mock()
    mock_gui.IsIconic.return_value = False
    mock_gui.GetForegroundWindow.side_effect = [500, 999]
    mock_process = Mock()
    mock_process.GetWindowThreadProcessId.return_value = (222, 333)
    mock_process.AttachThreadInput.side_effect = RuntimeError("Access is denied")
    mock_api = Mock()
    mock_api.GetCurrentThreadId.return_value = 111

    with patch("src.executor.windows.win32gui", mock_gui), \
         patch("src.executor.windows.win32process", mock_process), \
         patch.dict(sys.modules, {"win32api": mock_api}), \
         patch("src.executor.windows.win32con", Mock(SW_RESTORE=9)):
        assert executor.focus_window(999) is True
    mock_gui.SetForegroundWindow.assert_called_once_with(999)


