"""Tests for src/updater.py."""

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.updater import check_for_update, download_update, parse_version


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
