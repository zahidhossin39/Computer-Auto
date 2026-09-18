"""Native Windows OS automation and command execution."""

import ctypes
import os
import subprocess
from typing import Optional
import pyautogui
from src.config import IntentAction

try:
    import win32con
    import win32gui
except ImportError:
    win32con = None
    win32gui = None

# Windows Virtual Key Codes
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
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
        """Get HWND of foreground active window."""
        if win32gui is None:
            return None
        return win32gui.GetForegroundWindow()

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
            self._hotkey("alt", "f4")
            return True

        # System Lock
        elif command == "system_lock":
            ctypes.windll.user32.LockWorkStation()
            return True

        return False

    def launch_app(self, action: IntentAction) -> bool:
        """Launch a desktop application or fallback executable."""
        if not action.target:
            return False

        targets = [action.target]
        if action.fallback_target:
            targets.append(action.fallback_target)

        for target in targets:
            try:
                subprocess.Popen([target] + action.args, shell=True)
                return True
            except Exception:
                continue

        return False
