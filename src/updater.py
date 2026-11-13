"""GitHub Releases version checker and self-updater for Computer-Auto."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

APP_VERSION = "2.2.0"
GITHUB_REPO = "zahidhossin39/Computer-Auto"


@dataclass
class UpdateInfo:
    """Metadata for an available GitHub release update."""

    version: str
    tag_name: str
    download_url: str
    release_url: str
    notes: str = ""


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a semantic version string like 'v1.2.3' into a comparable tuple."""
    cleaned = version_str.strip().lstrip("vV").split("-", 1)[0]
    parts: list[int] = []
    for part in cleaned.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def check_for_update(
    current_version: str = APP_VERSION,
    repo: str = GITHUB_REPO,
    timeout: float = 10.0,
) -> Optional[UpdateInfo]:
    """Query GitHub Releases for a newer version; return UpdateInfo or None."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Computer-Auto/{current_version}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    tag_name = str(data.get("tag_name", "")).strip()
    if not tag_name or parse_version(tag_name) <= parse_version(current_version):
        return None

    assets = data.get("assets", []) or []
    installer_url = ""
    fallback_exe_url = ""
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if not name.endswith(".exe"):
            continue
        asset_url = str(asset.get("browser_download_url", ""))
        if not asset_url:
            continue
        if "setup" in name or "installer" in name:
            installer_url = asset_url
            break
        if not fallback_exe_url:
            fallback_exe_url = asset_url

    exe_url = installer_url or fallback_exe_url
    if not exe_url:
        return None

    return UpdateInfo(
        version=tag_name.lstrip("vV"),
        tag_name=tag_name,
        download_url=exe_url,
        release_url=str(data.get("html_url", f"https://github.com/{repo}/releases/latest")),
        notes=str(data.get("body", "")),
    )


def download_update(
    download_url: str,
    target_path: Path,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    timeout: float = 60.0,
) -> Path:
    """Download an update binary to target_path with optional progress callback."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": f"Computer-Auto/{APP_VERSION}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            with open(tmp_path, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb is not None:
                        progress_cb(downloaded, total)
        tmp_path.replace(target_path)
        return target_path
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def apply_windows_exe_update(new_exe_path: Path, current_exe_path: Optional[Path] = None) -> bool:
    """Schedule replacement of the running frozen .exe or launch a Windows Setup installer.

    Returns True if an update process was launched (caller should exit),
    or False when running from Python source (not frozen).
    """
    if not getattr(sys, "frozen", False):
        return False

    new_exe = Path(new_exe_path)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    lower_name = new_exe.name.lower()
    if "setup" in lower_name or "installer" in lower_name:
        subprocess.Popen([str(new_exe), "/S"], creationflags=creationflags)
        return True

    exe_path = Path(current_exe_path or sys.executable).resolve()
    pid = os.getpid()
    bat_path = Path(tempfile.gettempdir()) / f"computer_auto_update_{pid}.bat"
    script = (
        "@echo off\n"
        f":wait_loop\n"
        f"tasklist /FI \"PID eq {pid}\" 2>NUL | find /I \"{pid}\" >NUL\n"
        "if not errorlevel 1 (\n"
        "  timeout /t 1 /nobreak >NUL\n"
        "  goto wait_loop\n"
        ")\n"
        f"move /Y \"{new_exe}\" \"{exe_path}\" >NUL\n"
        f"start \"\" \"{exe_path}\"\n"
        "del \"%~f0\"\n"
    )
    bat_path.write_text(script, encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(bat_path)], creationflags=creationflags)
    return True
