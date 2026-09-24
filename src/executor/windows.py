"""Native Windows OS automation and command execution."""

import ctypes
import os
import shutil
import subprocess
import sys
import time
from typing import Optional
import pyautogui
from src.config import IntentAction


def ensure_default_desktop() -> None:
    """Ensure current thread is attached to the user's interactive 'Default' desktop.
    Fixes spawned GUI processes rendering into isolated virtual desktops (e.g. exebox-*)
    when executed from integrated IDE terminals.
    """
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            hDesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hDesk:
                user32.SetThreadDesktop(hDesk)
        except Exception:
            pass


def _shell_launch(target: str, args: str = "") -> bool:
    """ShellExecute via the desktop's explorer.exe (Raymond Chen's ShellWindows trick)."""
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()  # launch_app may run on worker threads
        # CLSID_ShellWindows; SWC_DESKTOP=8, SWFO_NEEDDISPATCH=1
        windows = win32com.client.Dispatch("{9BA05972-F6A8-11CF-A442-00A0C90A8F39}")
        desktop = windows.FindWindowSW(pythoncom.Empty, pythoncom.Empty, 8, 0, 1)
        desktop.Document.Application.ShellExecute(target, args, "", "open", 1)
        return True
    except Exception:
        return False


def type_text(text: str) -> None:
    """pyautogui.write silently drops anything outside ASCII (é, ñ, emoji): paste those."""
    if text.isascii():
        pyautogui.write(text, interval=0.01)
        return
    import win32clipboard
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    pyautogui.hotkey("ctrl", "v")  # ponytail: overwrites the user's clipboard; save/restore if it bites


try:
    import win32con
    import win32gui
    import win32process
except ImportError:
    win32con = None
    win32gui = None
    win32process = None

# Windows Virtual Key Codes
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_DELETE = 0x2E
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


class WindowsExecutor:
    """Dispatches deterministic actions to native Windows APIs and simulated inputs."""

    def __init__(self):
        # Allow mouse to be parked at corner without crashing daemon
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.05

    def _send_vk_code(self, vk_code: int) -> None:
        """Send virtual key using native Windows keybd_event API."""
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

    def _send_virtual_key(self, key_name: str) -> None:
        """Send virtual keypress by key name."""
        key_map = {
            "volumeup": VK_VOLUME_UP,
            "volumedown": VK_VOLUME_DOWN,
            "volumemute": VK_VOLUME_MUTE,
            "playpause": VK_MEDIA_PLAY_PAUSE,
            "nexttrack": VK_MEDIA_NEXT_TRACK,
            "prevtrack": VK_MEDIA_PREV_TRACK,
        }
        if key_name in key_map:
            self._send_vk_code(key_map[key_name])
        else:
            try:
                pyautogui.press(key_name)
            except Exception:
                pass

    def _hotkey(self, *keys: str) -> None:
        """Send combined hotkey press."""
        try:
            pyautogui.hotkey(*keys)
        except Exception:
            pass

    def _get_active_window(self) -> Optional[int]:
        """Get HWND of foreground active window.

        When the foreground window belongs to this process (our always-on-top
        Control Center), walk down the z-order and return the first visible,
        titled, non-minimised window owned by another process instead.
        """
        if win32gui is None:
            return None
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd or win32process is None:
            return hwnd
        if win32process.GetWindowThreadProcessId(hwnd)[1] != os.getpid():
            return hwnd
        hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)
        while hwnd:
            if (
                win32gui.IsWindowVisible(hwnd)
                and win32gui.GetWindowText(hwnd)
                and not win32gui.IsIconic(hwnd)
                and win32process.GetWindowThreadProcessId(hwnd)[1] != os.getpid()
            ):
                return hwnd
            hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)
        return None

    def execute_system_action(self, command: str) -> bool:
        """Execute system or window action by command identifier."""
        # Volume
        if command == "volume_step_up":
            self._send_virtual_key("volumeup")
            return True
        elif command == "volume_step_down":
            self._send_virtual_key("volumedown")
            return True
        elif command == "volume_toggle_mute":
            self._send_virtual_key("volumemute")
            return True

        # Media
        elif command == "media_play_pause":
            self._send_virtual_key("playpause")
            return True
        elif command == "media_next":
            self._send_virtual_key("nexttrack")
            return True
        elif command == "media_previous":
            self._send_virtual_key("prevtrack")
            return True

        # Window Snap
        elif command == "window_snap_left":
            self._hotkey("win", "left")
            return True
        elif command == "window_snap_right":
            self._hotkey("win", "right")
            return True

        # Window States
        elif command == "window_minimize_active":
            hwnd = self._get_active_window()
            if hwnd and win32gui and win32con:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            else:
                self._hotkey("win", "down")
            return True

        elif command == "window_maximize_active":
            hwnd = self._get_active_window()
            if hwnd and win32gui and win32con:
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            else:
                self._hotkey("win", "up")
            return True

        elif command == "window_restore_active":
            hwnd = self._get_active_window()
            if hwnd and win32gui and win32con:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            return True

        elif command == "window_close_active":
            # Alt+F4 hits whatever holds focus, which closed our own Control Center.
            # _get_active_window() skips our windows, so close that one directly.
            hwnd = self._get_active_window()
            if hwnd and win32gui and win32con:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                return True
            return False

        # System Lock
        elif command == "system_lock":
            ctypes.windll.user32.LockWorkStation()
            return True

        # Key Presses
        elif command == "key_enter":
            self._send_vk_code(VK_RETURN)
            return True
        elif command == "key_escape":
            self._send_vk_code(VK_ESCAPE)
            return True
        elif command == "key_tab":
            self._send_vk_code(VK_TAB)
            return True
        elif command == "key_backspace":
            self._send_vk_code(VK_BACK)
            return True
        elif command == "key_delete":
            self._send_vk_code(VK_DELETE)
            return True
        elif command == "key_page_down":
            self._send_vk_code(VK_NEXT)
            return True
        elif command == "key_page_up":
            self._send_vk_code(VK_PRIOR)
            return True

        return False

    def _focus_target(self) -> None:
        """Keys go to the focused window; if that is our own shell, hand focus back first."""
        hwnd = self._get_active_window()
        if hwnd and win32gui and hwnd != win32gui.GetForegroundWindow():
            try:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.15)
            except Exception:
                pass

    def run_action(self, action: IntentAction) -> bool:
        """hotkey / open_app / type_text / open_url intents: no vision call needed."""
        try:
            if action.type == "hotkey" and action.keys:
                self._focus_target()
                pyautogui.hotkey(*action.keys)
            elif action.type == "type_text" and action.target:
                self._focus_target()
                type_text(action.target)
            elif action.type == "open_app" and action.target:
                explorer = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "explorer.exe")
                return _shell_launch(explorer, f"shell:AppsFolder\\{action.target}")
            elif action.type == "open_url" and action.target:
                return _shell_launch(action.target)
            else:
                return False
            return True
        except Exception as e:
            print(f"[EXECUTOR]: {action.type} failed ({e})")
            return False

    def launch_app(self, action: IntentAction) -> bool:
        """Launch a desktop application or fallback executable."""
        if not action.target:
            return False

        ensure_default_desktop()

        targets = [action.target]
        if action.fallback_target:
            targets.append(action.fallback_target)

        for target in targets:
            # Resolve executable to an absolute path via PATH if available.
            # CRITICAL: On Windows 10/11, relative 'notepad.exe' invokes the UWP/MSIX App Execution Alias
            # (%LOCALAPPDATA%\Microsoft\WindowsApps\notepad.exe) which creates a suspended/invisible
            # background process when launched from an IDE/terminal. Resolving via shutil.which yields
            # 'C:\Windows\System32\notepad.exe' which reliably opens an interactive visible GUI window.
            resolved_target = shutil.which(target) or target

            # 0. Ask the running explorer.exe to launch it. The child is then parented by explorer,
            # escaping any IDE sandbox/job/desktop our own process is stuck in.
            if os.path.isfile(resolved_target) and _shell_launch(resolved_target, " ".join(action.args)):
                return True

            # 1. On Windows, use os.startfile to ensure the process launches
            # onto the user's interactive 'Default' desktop station (WinSta0\Default),
            # preventing invisible windows when launched from sandboxed/IDE terminals.
            if hasattr(os, "startfile"):
                try:
                    args_str = " ".join(action.args) if action.args else ""
                    if args_str:
                        os.startfile(resolved_target, "open", arguments=args_str)
                    else:
                        os.startfile(resolved_target)
                    return True
                except Exception:
                    pass

            # 2. Fallback to subprocess.Popen with WinSta0\Default desktop
            try:
                startupinfo = None
                if sys.platform == "win32":
                    try:
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.lpDesktop = r"WinSta0\Default"
                    except Exception:
                        startupinfo = None

                # Avoid shell=True because cmd.exe drops lpDesktop inheritance for child processes
                if startupinfo:
                    subprocess.Popen([resolved_target] + action.args, startupinfo=startupinfo)
                else:
                    subprocess.Popen([resolved_target] + action.args)
                return True
            except Exception:
                continue

        return False

