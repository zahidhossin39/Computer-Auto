"""Installed-app index: resolve a spoken app name ("cloud code") to a Start menu app (Claude Code).

Get-StartApps lists every app the Start menu can launch (desktop and Store) with an AppID
that `shell:AppsFolder\\<AppID>` opens, so one source covers both kinds.
"""

import difflib
import json
import subprocess
import threading
from typing import Dict, Optional, Tuple

from src import jev

_apps: Dict[str, str] = {}  # lower-case name -> AppID
_names: Dict[str, str] = {}  # lower-case name -> display name
_loaded = threading.Event()


def load() -> None:
    """Read the Start menu app list (~1s). Call once from a background thread."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        for a in json.loads(out or "[]"):
            if a.get("Name") and a.get("AppID"):
                _apps[a["Name"].lower()] = a["AppID"]
                _names[a["Name"].lower()] = a["Name"]
        print(f"[APPS]: indexed {len(_apps)} Start menu apps")
    except Exception as e:
        print(f"[APPS]: could not read Start menu apps ({e})")
    finally:
        _loaded.set()


def find(spoken: str) -> Optional[Tuple[str, str]]:
    """(display name, AppID) of the app the user most likely meant, or None."""
    _loaded.wait(timeout=5)
    q = spoken.lower().strip()
    if not q or not _apps:
        return None
    if q in _apps:
        return _names[q], _apps[q]
    # Speech recognition mangles brand names ("cloud" for "Claude"): fuzzy match first
    close = difflib.get_close_matches(q, list(_apps), n=1, cutoff=0.75)
    if close:
        return _names[close[0]], _apps[close[0]]
    # "chrome" -> "Google Chrome": a name that contains every spoken word
    words = q.split()
    hits = [n for n in _apps if all(w in n.split() for w in words)]
    if len(hits) == 1:
        return _names[hits[0]], _apps[hits[0]]
    if len(words) > 3:
        return None  # a sentence, not an app name: let the vision agent read it
    names = list(_apps)[:254]
    picked = jev.choose(
        {"spoken_app_name": spoken, "note": "text comes from speech recognition and may be misheard"},
        "Which installed app did the user ask to open? Answer none if no app fits.",
        {**{str(i): _names[n] for i, n in enumerate(names)}, "none": "No installed app matches"},
    )
    if picked and picked[0] != "none" and picked[1] >= 0.8:
        n = names[int(picked[0])]
        return _names[n], _apps[n]
    return None


def open_windows() -> list:
    """(hwnd, title, exe name) of visible top-level windows, front-most first, minus ours."""
    import os
    import win32api
    import win32con
    import win32gui
    import win32process
    out = []

    def add(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if not title or not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        if pid == os.getpid():
            return
        try:
            h = win32api.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            exe = os.path.basename(win32process.GetModuleFileNameEx(h, 0)).lower()
        except Exception:
            exe = ""
        out.append((hwnd, title, exe))

    win32gui.EnumWindows(add, None)
    return out


def find_window(spoken: str):
    """(hwnd, title) of the open window the user named ("chrome", "the notepad"), or None."""
    words = [w for w in spoken.lower().split() if w not in ("the", "my", "a", "this", "that", "it", "window", "app")]
    if not words:
        return None
    wins = open_windows()
    for hwnd, title, exe in wins:  # front-most first, so "chrome" means the Chrome you last used
        hay = f"{title.lower()} {exe[:-4]}"
        if all(w in hay for w in words):
            return hwnd, title
    # "note pad", "vs code": resolve through the app index, then match its name
    app = find(" ".join(words))
    if app:
        name = app[0].lower()
        for hwnd, title, exe in wins:
            if name in title.lower() or name.split()[-1] in exe:
                return hwnd, title
    return None


if __name__ == "__main__":
    load()
    for s in ("claude", "cloud code", "chrome", "discord", "vs code", "calculator", "banana split"):
        print(s, "->", find(s))
