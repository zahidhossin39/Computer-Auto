"""Installed-app index: resolve a spoken app name ("cloud code") to a Start menu app (Claude Code).

Get-StartApps lists every app the Start menu can launch (desktop and Store) with an AppID
that `shell:AppsFolder\\<AppID>` opens, so one source covers both kinds.
"""

import difflib
import os
import re
import json
import subprocess
import threading
from typing import Any, Dict, List, Optional, Tuple

from src import jev

_apps: Dict[str, str] = {}  # lower-case name -> AppID
_names: Dict[str, str] = {}  # lower-case name -> display name
_loaded = threading.Event()
_load_started = False
_load_lock = threading.Lock()
_chrome_profiles_cache: Tuple[str, float, List[Dict[str, Any]]] = ("", -1.0, [])

COMMON_APPS = {
    "notepad": ("Notepad", "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"),
    "terminal": ("Terminal", "Microsoft.WindowsTerminal_8wekyb3d8bbwe!App"),
    "calculator": ("Calculator", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
    "settings": ("Settings", "windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel"),
    "paint": ("Paint", "Microsoft.Paint_8wekyb3d8bbwe!App"),
    "chrome": ("Google Chrome", "Chrome"),
    "discord": ("Discord", "com.squirrel.Discord.Discord"),
    "spotify": ("Spotify", "Spotify"),
    "code": ("Visual Studio Code", "Microsoft.VisualStudioCode"),
    "claude": ("Claude", "Claude_pzs8sxrjxfjjc!Claude"),
}


ORDINAL_MAP = {
    "1": 1, "1st": 1, "first": 1, "one": 1, "won": 1, "initial": 1, "primary": 1, "default": 1, "main": 1,
    "2": 2, "2nd": 2, "second": 2, "two": 2, "too": 2,
    "3": 3, "3rd": 3, "third": 3, "three": 3, "tree": 3,
    "4": 4, "4th": 4, "fourth": 4, "four": 4, "forth": 4,
    "5": 5, "5th": 5, "fifth": 5, "five": 5,
    "6": 6, "6th": 6, "sixth": 6, "six": 6,
    "7": 7, "7th": 7, "seventh": 7, "seven": 7,
    "8": 8, "8th": 8, "eighth": 8, "eight": 8,
    "9": 9, "9th": 9, "ninth": 9, "nine": 9,
    "10": 10, "10th": 10, "tenth": 10, "ten": 10,
}

GENERIC_PROFILE_WORDS = {
    "open", "launch", "start", "run", "switch", "go", "to", "back", "focus", "show",
    "bring", "up", "choose", "select", "pick", "click", "use", "chrome", "google",
    "browser", "gmail", "mail", "email", "inbox", "account", "accounts", "profile",
    "profiles", "number", "no", "num", "the", "my", "a", "an", "this", "that", "in",
    "on", "of", "for", "from", "with", "please", "is", "already", "opened",
}


def _profile_sort_key(prof_dir: str) -> Tuple[int, int, str]:
    if prof_dir == "Default":
        return (0, 0, "")
    m = re.match(r"^Profile\s+(\d+)$", prof_dir, re.I)
    if m:
        return (1, int(m.group(1)), prof_dir)
    return (2, 0, prof_dir)


def chrome_profiles(local_state_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return ordered list of Chrome profiles with index, dir, name, and email from Local State."""
    global _chrome_profiles_cache
    if local_state_path is None:
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if not local_appdata:
            return []
        local_state_path = os.path.join(local_appdata, "Google", "Chrome", "User Data", "Local State")

    try:
        if not os.path.isfile(local_state_path):
            return []
        mtime = os.path.getmtime(local_state_path)
        if _chrome_profiles_cache[0] == local_state_path and _chrome_profiles_cache[1] == mtime:
            return list(_chrome_profiles_cache[2])

        with open(local_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile_sec = data.get("profile", {}) if isinstance(data, dict) else {}
        info_cache = profile_sec.get("info_cache", {}) if isinstance(profile_sec, dict) else {}
        if not isinstance(info_cache, dict) or not info_cache:
            return []

        raw_order = profile_sec.get("profiles_order", [])
        ordered_dirs: List[str] = []
        if isinstance(raw_order, list):
            for d in raw_order:
                if isinstance(d, str) and d in info_cache and d not in ordered_dirs:
                    ordered_dirs.append(d)

        remaining = sorted(
            (k for k in info_cache.keys() if k not in ordered_dirs),
            key=_profile_sort_key,
        )
        ordered_dirs.extend(remaining)

        result: List[Dict[str, Any]] = []
        for idx, prof_dir in enumerate(ordered_dirs, 1):
            meta = info_cache.get(prof_dir) or {}
            if not isinstance(meta, dict):
                meta = {}
            name = str(meta.get("name") or meta.get("shortcut_name") or prof_dir).strip()
            email = str(meta.get("user_name") or "").strip()
            gaia_name = str(meta.get("gaia_name") or "").strip()
            shortcut_name = str(meta.get("shortcut_name") or "").strip()
            result.append({
                "index": idx,
                "dir": prof_dir,
                "name": name,
                "email": email,
                "gaia_name": gaia_name,
                "shortcut_name": shortcut_name,
            })

        _chrome_profiles_cache = (local_state_path, mtime, result)
        return list(result)
    except Exception:
        return []


def find_chrome_profile(query: str, local_state_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Resolve a spoken/typed Chrome profile or Gmail specifier ('3rd', 'third number', '5', 'work') to a profile."""
    q = (query or "").lower().strip()
    if not q:
        return None

    profiles = chrome_profiles() if local_state_path is None else chrome_profiles(local_state_path=local_state_path)
    tokens = re.findall(r"[a-z0-9._-]+", q)
    if not tokens:
        return None

    # 1. Check "last" / "final"
    if any(t in ("last", "final") for t in tokens):
        if profiles:
            return profiles[-1]

    # 2. Check ordinal / number tokens (1..10, 1st..10th, first..tenth, default/primary)
    for tok in tokens:
        if tok in ORDINAL_MAP:
            idx = ORDINAL_MAP[tok]
            if profiles:
                if 1 <= idx <= len(profiles):
                    return profiles[idx - 1]
                for p in profiles:
                    if p["dir"].lower() == f"profile {idx}":
                        return p
                return None
            # Fallback if Local State is unavailable
            prof_dir = "Default" if idx == 1 else f"Profile {idx}"
            return {
                "index": idx,
                "dir": prof_dir,
                "name": prof_dir,
                "email": "",
                "gaia_name": "",
                "shortcut_name": "",
            }

    # 3. Match by email handle, profile display name, or gaia_name
    rem_tokens = [t for t in tokens if t not in GENERIC_PROFILE_WORDS]
    if rem_tokens and profiles:
        best_prof = None
        best_score = 0
        for p in profiles:
            email_lower = str(p.get("email", "")).lower()
            email_user = email_lower.split("@")[0] if "@" in email_lower else email_lower
            name_lower = str(p.get("name", "")).lower()
            gaia_lower = str(p.get("gaia_name", "")).lower()
            shortcut_lower = str(p.get("shortcut_name", "")).lower()
            dir_lower = str(p.get("dir", "")).lower()
            searchable = f"{email_user} {email_lower} {name_lower} {gaia_lower} {shortcut_lower} {dir_lower}"
            word_parts = set(re.findall(r"[a-z0-9]+", searchable))

            if all(t in searchable for t in rem_tokens):
                score = 1
                if all(t in word_parts for t in rem_tokens):
                    score += 3
                if any(t in email_user for t in rem_tokens):
                    score += 2
                if any(t == name_lower or t == shortcut_lower for t in rem_tokens):
                    score += 2
                if score > best_score:
                    best_score = score
                    best_prof = p
        if best_prof is not None:
            return best_prof

    return None


def ensure_load_started() -> None:
    """Ensure the Start menu index background loader has been triggered."""
    global _load_started
    with _load_lock:
        if not _load_started:
            _load_started = True
            threading.Thread(target=load, daemon=True).start()


def load() -> None:
    """Read the Start menu app list (~1s). Call once from a background thread."""
    global _load_started
    _load_started = True
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


def find(spoken: str, allow_jev: bool = True) -> Optional[Tuple[str, str]]:
    """(display name, AppID) of the app the user most likely meant, or None."""
    q = spoken.lower().strip()
    if not q:
        return None
    if _apps and q in _apps:
        return _names[q], _apps[q]
    # Check pre-seeded common system apps first for zero-latency lookup
    if q in COMMON_APPS:
        return COMMON_APPS[q]

    ensure_load_started()
    if not _loaded.is_set():
        _loaded.wait(timeout=0.5)
    if not _apps:
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
    if not allow_jev or len(words) > 3:
        return None  # a sentence, not an app name, or Jev lookup disabled: let caller handle it
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


def ensure_desktop_attached() -> None:
    """Ensure current thread is attached to the user's interactive desktop station."""
    import sys
    if sys.platform != "win32":
        return
    import ctypes
    try:
        user32 = ctypes.windll.user32
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if not hdesk:
            hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x01FF)
            if hwinsta:
                user32.SetProcessWindowStation(hwinsta)
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def open_windows() -> list:
    """(hwnd, title, exe name) of visible top-level windows, front-most first, minus ours."""
    ensure_desktop_attached()
    import os
    import win32api
    import win32con
    import win32gui
    import win32process
    out = []
    parent_pid = os.getppid() if hasattr(os, "getppid") else -1
    my_pid = os.getpid()

    def add(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if not title or not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        if pid in (my_pid, parent_pid):
            return
        lower_title = title.lower()
        if "computer-auto" in lower_title or lower_title.startswith("computer-auto"):
            return
        try:
            h = win32api.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            exe = os.path.basename(win32process.GetModuleFileNameEx(h, 0)).lower()
        except Exception:
            exe = ""
        if exe.startswith("computer-auto"):
            return
        out.append((hwnd, title, exe))

    try:
        win32gui.EnumWindows(add, None)
    except Exception:
        pass
    return out


PHONETIC_WINDOW_ALIASES = {
    "not pet": "notepad",
    "not bad": "notepad",
    "note bad": "notepad",
    "not pad": "notepad",
    "cloud": "claude",
    "cloud code": "claude",
    "dis cord": "discord",
    "dis chord": "discord",
    "spot ify": "spotify",
    "fire fox": "firefox",
    "vs code": "code",
    "visual studio code": "code",
    "visual studio": "code",
    "power shell": "powershell",
    "terminal": "terminal",
    "wt": "terminal",
    "msedge": "edge",
    "google chrome": "chrome",
    "minima's": "minimize",
    "minimas": "minimize",
    "minimise": "minimize",
    "minimised": "minimize",
    "upset": "website",
    "this upset": "this website",
}

CATEGORY_WINDOW_EXES = {
    "browser": ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"),
    "web browser": ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"),
    "terminal": ("windowsterminal.exe", "cmd.exe", "powershell.exe", "wt.exe", "conhost.exe"),
    "console": ("windowsterminal.exe", "cmd.exe", "powershell.exe", "wt.exe", "conhost.exe"),
    "command prompt": ("cmd.exe", "windowsterminal.exe"),
    "editor": ("notepad.exe", "code.exe"),
    "text editor": ("notepad.exe", "code.exe"),
}

WINDOW_FILLER_WORDS = {
    "the", "my", "a", "an", "this", "that", "it", "window", "app", "application",
    "program", "which", "is", "are", "was", "already", "open", "opened", "opening",
    "running", "active", "on", "in", "at", "to", "from", "screen", "desktop",
    "monitor", "currently", "right", "now", "please", "back", "up",
}


def find_window(spoken: str):
    """(hwnd, title) of the open window the user named ("chrome", "the notepad", "the browser"), or None."""
    lower_spoken = re.sub(r"\.exe\b", "", spoken.lower().strip())
    for phrase, alias in PHONETIC_WINDOW_ALIASES.items():
        if phrase in lower_spoken:
            lower_spoken = lower_spoken.replace(phrase, alias)

    words = [w for w in re.findall(r"[a-z0-9_-]+", lower_spoken) if w not in WINDOW_FILLER_WORDS]
    if not words:
        # If user explicitly said "this window" or "this app" or "active window"
        wins = open_windows()
        if wins:
            return wins[0][0], wins[0][1]
        return None

    wins = [(w[0], w[1], w[2] if len(w) > 2 else "") for w in open_windows()]

    # Strip generic category words when a specific app name is also present ("chrome browser" -> "chrome")
    generic_cats = {"browser", "web", "editor", "text", "terminal", "console"}
    specific_words = [w for w in words if w not in generic_cats] or words

    # 1. Exact or whole-word match on specific words
    for candidate_words in (words, specific_words):
        for hwnd, title, exe in wins:  # front-most first
            exe_stem = exe[:-4] if exe.endswith(".exe") else exe
            hay = set(re.findall(r"\w+", f"{title.lower()} {exe_stem}"))
            if all(w in hay for w in candidate_words):
                return hwnd, title

    # 2. Substring match (e.g. 'terminal' in 'windowsterminal', or 'discord' in title)
    for candidate_words in (words, specific_words):
        for hwnd, title, exe in wins:
            exe_stem = exe[:-4] if exe.endswith(".exe") else exe
            combined = f"{title.lower()} {exe_stem}"
            if all(w in combined for w in candidate_words):
                return hwnd, title

    # 3. Category matching (e.g. "browser", "the terminal")
    target_phrase = " ".join(words)
    for cat_name, exe_list in CATEGORY_WINDOW_EXES.items():
        if cat_name in target_phrase or any(w == cat_name for w in words):
            for hwnd, title, exe in wins:
                if exe in exe_list or any(stem in exe for stem in [e[:-4] for e in exe_list]):
                    return hwnd, title

    # 4. Installed app index match
    app = find(" ".join(specific_words), allow_jev=False)
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
