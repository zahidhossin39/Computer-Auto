"""Tests for src/updater.py."""

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.updater import (
    APP_VERSION,
    apply_windows_exe_update,
    check_for_update,
    download_update,
    parse_version,
)


def test_app_version_is_v2():
    assert APP_VERSION == "2.5.1"


def test_parse_version():
    assert parse_version("v1.0.0") == (1, 0, 0)
    assert parse_version("1.2.10") > parse_version("v1.2.9")
    assert parse_version("v2.0.0-beta") == (2, 0, 0)


def test_check_for_update_returns_info_when_newer():
    payload = {
        "tag_name": "v1.1.0",
        "html_url": "https://github.com/zahidhossin39/Computer-Auto/releases/tag/v1.1.0",
        "body": "Bug fixes",
        "assets": [
            {
                "name": "Computer-Auto.exe",
                "browser_download_url": "https://example.com/Computer-Auto.exe",
            }
        ],
    }
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=resp):
        info = check_for_update(current_version="1.0.0")

    assert info is not None
    assert info.version == "1.1.0"
    assert info.download_url == "https://example.com/Computer-Auto.exe"


def test_check_for_update_returns_none_when_up_to_date():
    payload = {
        "tag_name": "v1.0.0",
        "assets": [
            {"name": "Computer-Auto.exe", "browser_download_url": "https://example.com/Computer-Auto.exe"}
        ],
    }
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=resp):
        assert check_for_update(current_version="1.0.0") is None


def test_download_update_writes_file_and_reports_progress(tmp_path: Path):
    content = b"MZ-fake-exe-payload"
    stream = io.BytesIO(content)
    resp = MagicMock()
    resp.headers = {"Content-Length": str(len(content))}
    resp.read.side_effect = stream.read
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False

    progress_calls = []
    dest = tmp_path / "Computer-Auto.exe.new"
    with patch("urllib.request.urlopen", return_value=resp):
        out = download_update("https://example.com/Computer-Auto.exe", dest, progress_cb=lambda d, t: progress_calls.append((d, t)))

    assert out == dest
    assert dest.read_bytes() == content
    assert progress_calls[-1] == (len(content), len(content))


def test_check_for_update_prefers_setup_installer_over_standalone_exe():
    payload = {
        "tag_name": "v2.1.0",
        "html_url": "https://github.com/zahidhossin39/Computer-Auto/releases/tag/v2.1.0",
        "body": "v2.1.0 release",
        "assets": [
            {
                "name": "Computer-Auto.exe",
                "browser_download_url": "https://example.com/Computer-Auto.exe",
            },
            {
                "name": "Computer-Auto-Setup.exe",
                "browser_download_url": "https://example.com/Computer-Auto-Setup.exe",
            },
        ],
    }
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=resp):
        info = check_for_update(current_version="2.0.0")

    assert info is not None
    assert info.version == "2.1.0"
    assert info.download_url == "https://example.com/Computer-Auto-Setup.exe"


def test_apply_windows_exe_update_returns_false_when_not_frozen(tmp_path: Path):
    installer = tmp_path / "Computer-Auto-Setup.exe"
    installer.write_bytes(b"MZ")
    with patch.object(sys, "frozen", False, create=True):
        assert apply_windows_exe_update(installer) is False


def test_apply_windows_exe_update_launches_setup_installer_directly(tmp_path: Path):
    installer = tmp_path / "Computer-Auto-Setup.exe"
    installer.write_bytes(b"MZ")
    expected_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    with patch.object(sys, "frozen", True, create=True), patch("subprocess.Popen") as mock_popen:
        launched = apply_windows_exe_update(installer)

    assert launched is True
    mock_popen.assert_called_once_with([str(installer), "/S"], creationflags=expected_flags)


def test_apply_windows_exe_update_uses_bat_for_standalone_exe(tmp_path: Path):
    new_exe = tmp_path / "Computer-Auto.exe.new"
    current_exe = tmp_path / "Computer-Auto.exe"
    new_exe.write_bytes(b"MZ")
    current_exe.write_bytes(b"MZ")
    expected_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    with (
        patch.object(sys, "frozen", True, create=True),
        patch("tempfile.gettempdir", return_value=str(tmp_path)),
        patch("subprocess.Popen") as mock_popen,
    ):
        launched = apply_windows_exe_update(new_exe, current_exe_path=current_exe)

    assert launched is True
    args, kwargs = mock_popen.call_args
    assert args[0][0:2] == ["cmd", "/c"]
    bat_file = Path(args[0][2])
    assert bat_file.exists()
    bat_text = bat_file.read_text(encoding="utf-8")
    assert "move /Y" in bat_text
    assert str(new_exe) in bat_text
    assert str(current_exe.resolve()) in bat_text
    assert kwargs["creationflags"] == expected_flags
