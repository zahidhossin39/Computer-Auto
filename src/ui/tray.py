"""Lightweight Win32 System Tray icon using pywin32 (safe no-op fallback)."""

import sys
import threading
from typing import Callable, Optional

try:
    if sys.platform == "win32":
        import win32api
        import win32con
        import win32gui
        _HAS_WIN32 = True
    else:
        _HAS_WIN32 = False
except Exception:
    _HAS_WIN32 = False


WM_TRAY_CALLBACK = 0x0400 + 20  # WM_USER + 20
_CMD_SHOW = 1001
_CMD_TOGGLE = 1002
_CMD_QUIT = 1003


class TrayIcon:
    """Optional Win32 notification area icon with Show, Toggle Mic, and Quit actions."""

    def __init__(
        self,
        on_restore: Optional[Callable[[], None]] = None,
        on_toggle_listening: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        tooltip: str = "Computer-Auto",
    ):
        self.on_restore = on_restore
        self.on_toggle_listening = on_toggle_listening
        self.on_quit = on_quit
        self.tooltip = tooltip[:127]

        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._class_atom = None
        self._nid = None

    @property
    def is_available(self) -> bool:
        return _HAS_WIN32

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Start the Win32 tray icon message loop on a daemon thread. Returns True if started."""
        if not _HAS_WIN32 or self._running:
            return False
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="tray-icon", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Remove the tray icon and stop the Win32 message loop."""
        self._running = False
        hwnd = self._hwnd
        if hwnd and _HAS_WIN32:
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        self._hwnd = None
        self._nid = None

    def update_tooltip(self, text: str) -> None:
        """Update the tray hover tooltip if the icon is currently active."""
        self.tooltip = text[:127]
        if not _HAS_WIN32 or not self._hwnd or not self._nid:
            return
        try:
            hicon = self._nid[4]
            nid = (
                self._hwnd,
                0,
                win32gui.NIF_TIP,
                WM_TRAY_CALLBACK,
                hicon,
                self.tooltip,
            )
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)
        except Exception:
            pass

    def _run_loop(self) -> None:
        try:
            hinst = win32api.GetModuleHandle(None)
            class_name = f"ComputerAutoTray_{id(self)}"
            wndclass = win32gui.WNDCLASS()
            wndclass.hInstance = hinst
            wndclass.lpszClassName = class_name
            wndclass.lpfnWndProc = {
                win32con.WM_DESTROY: self._on_destroy,
                win32con.WM_CLOSE: self._on_close,
                win32con.WM_COMMAND: self._on_command,
                WM_TRAY_CALLBACK: self._on_tray_notify,
            }
            self._class_atom = win32gui.RegisterClass(wndclass)
            self._hwnd = win32gui.CreateWindow(
                self._class_atom,
                "Computer-Auto Tray",
                0,
                0,
                0,
                win32con.CW_USEDEFAULT,
                win32con.CW_USEDEFAULT,
                0,
                0,
                hinst,
                None,
            )
            hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
            flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
            self._nid = (self._hwnd, 0, flags, WM_TRAY_CALLBACK, hicon, self.tooltip)
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, self._nid)
            win32gui.PumpMessages()
        except Exception:
            self._running = False
        finally:
            self._cleanup_notify_icon()

    def _cleanup_notify_icon(self) -> None:
        if self._hwnd and _HAS_WIN32:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self._hwnd, 0))
            except Exception:
                pass
        self._nid = None

    def _on_close(self, hwnd, msg, wparam, lparam):
        self._cleanup_notify_icon()
        win32gui.DestroyWindow(hwnd)
        return 0

    def _on_destroy(self, hwnd, msg, wparam, lparam):
        self._cleanup_notify_icon()
        win32gui.PostQuitMessage(0)
        return 0

    def _on_tray_notify(self, hwnd, msg, wparam, lparam):
        if lparam in (win32con.WM_LBUTTONUP, win32con.WM_LBUTTONDBLCLK):
            if self.on_restore:
                self.on_restore()
        elif lparam == win32con.WM_RBUTTONUP:
            self._show_menu(hwnd)
        return 0

    def _show_menu(self, hwnd: int) -> None:
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, _CMD_SHOW, "Show Computer-Auto")
        win32gui.AppendMenu(menu, win32con.MF_STRING, _CMD_TOGGLE, "Start / Stop Listening")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, _CMD_QUIT, "Quit")
        pos = win32gui.GetCursorPos()
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN | win32con.TPM_BOTTOMALIGN,
            pos[0],
            pos[1],
            0,
            hwnd,
            None,
        )
        win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)

    def _on_command(self, hwnd, msg, wparam, lparam):
        cmd_id = win32api.LOWORD(wparam)
        if cmd_id == _CMD_SHOW and self.on_restore:
            self.on_restore()
        elif cmd_id == _CMD_TOGGLE and self.on_toggle_listening:
            self.on_toggle_listening()
        elif cmd_id == _CMD_QUIT and self.on_quit:
            self.on_quit()
        return 0
