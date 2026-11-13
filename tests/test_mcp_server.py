"""Unit and end-to-end stdio tests for src/mcp_server.py."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from src import history, learned, mcp_server


@pytest.fixture(autouse=True)
def isolated_mcp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect history.jsonl and learned_commands.json to tmp_path."""
    learned_file = tmp_path / "learned_commands.json"
    hist_file = tmp_path / "history.jsonl"
    monkeypatch.setenv("COMPUTER_AUTO_LEARNED_PATH", str(learned_file))
    monkeypatch.setenv("COMPUTER_AUTO_HISTORY_PATH", str(hist_file))
    monkeypatch.setattr(learned, "LEARNED_PATH", learned_file)
    monkeypatch.setattr(history, "HISTORY_PATH", hist_file)
    yield learned_file, hist_file


def _call_tool(name: str, arguments: dict | None = None, req_id: int = 1) -> tuple[dict, bool]:
    resp = mcp_server.handle_jsonrpc_message({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    })
    assert resp is not None
    result = resp["result"]
    is_err = bool(result.get("isError", False))
    payload = json.loads(result["content"][0]["text"])
    return payload, is_err


def test_mcp_initialize_and_tools_list():
    """Verify initialize and tools/list expose all 10 required MCP tools."""
    init_resp = mcp_server.handle_jsonrpc_message({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
    })
    assert init_resp is not None
    assert init_resp["result"]["serverInfo"]["name"] == "computer-auto"

    list_resp = mcp_server.handle_jsonrpc_message({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    })
    assert list_resp is not None
    tools = list_resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    expected = {
        "get_history",
        "get_vision_tasks",
        "list_commands",
        "list_builtin_intents",
        "suggest_commands",
        "create_command",
        "update_command",
        "delete_command",
        "approve_suggestion",
        "test_route",
    }
    assert expected.issubset(tool_names)
    for t in tools:
        assert len(t.get("description", "")) >= 40


def test_mcp_full_agent_learning_workflow():
    """Simulate an external MCP agent inspecting history, creating/approving commands, and testing routing."""
    # 1. Seed history with repeated Vision tasks and a keyword task
    history.record_event("volume up", "keyword", "volume_up", [{"type": "system_action", "command": "volume_step_up"}], True, 10)
    for _ in range(2):
        history.record_event(
            "open slack threads",
            "vision",
            None,
            [{"action": "click", "target": "Threads", "x": 80, "y": 220}],
            True,
            2100,
        )

    # 2. Agent calls get_history and get_vision_tasks
    hist_data, err = _call_tool("get_history", {"limit": 50})
    assert not err and hist_data["count"] == 3

    vis_data, err = _call_tool("get_vision_tasks", {"limit": 50})
    assert not err and vis_data["count"] == 2
    assert vis_data["events"][0]["route"] == "vision"

    # 3. Agent inspects built-in intents
    builtins, err = _call_tool("list_builtin_intents")
    assert not err and builtins["count"] > 5

    # 4. Agent runs suggest_commands -> gets unapproved suggestion
    sug_data, err = _call_tool("suggest_commands", {"min_occurrences": 2})
    assert not err and sug_data["count"] == 1
    sug_id = sug_data["suggestions"][0]["id"]

    # Before approval, test_route shows "open slack threads" still goes to vision
    route_before, err = _call_tool("test_route", {"utterance": "open slack threads"})
    assert not err
    assert route_before["is_vision"] is True
    assert route_before["tier"] == "vision"

    # 5. Agent approves suggestion -> test_route now hits 'learned' tier
    app_data, err = _call_tool("approve_suggestion", {"id": sug_id})
    assert not err and app_data["command"]["enabled"] is True

    route_after, err = _call_tool("test_route", {"utterance": "open slack threads"})
    assert not err
    assert route_after["is_vision"] is False
    assert route_after["tier"] == "learned"

    # 6. Agent creates a custom multi-step command from scratch
    created, err = _call_tool(
        "create_command",
        {
            "name": "focus_and_new_tab",
            "description": "Open a new browser tab via hotkey",
            "triggers": ["make a fresh tab", "pop open a tab"],
            "steps": [
                {"type": "hotkey", "keys": ["ctrl", "t"]},
                {"type": "wait", "command": "200"},
            ],
        },
    )
    assert not err
    cid = created["command"]["id"]

    # 7. Update command triggers
    updated, err = _call_tool(
        "update_command",
        {"id": cid, "triggers": ["make a fresh tab", "pop open a tab", "spawn tab"]},
    )
    assert not err
    assert "spawn tab" in updated["command"]["triggers"]

    # Verify test_route hits the new trigger
    tr, err = _call_tool("test_route", {"utterance": "please spawn tab"})
    assert not err and tr["tier"] == "learned" and tr["intent_name"] == "focus_and_new_tab"

    # 8. List & delete
    listed, err = _call_tool("list_commands")
    assert not err and listed["count"] == 2

    deleted, err = _call_tool("delete_command", {"id": cid})
    assert not err and deleted["deleted"] is True


def test_mcp_rejects_dangerous_command_steps():
    """create_command returns isError=True when given shell commands or raw pixel coordinates."""
    payload, is_err = _call_tool(
        "create_command",
        {
            "name": "evil_cmd",
            "description": "Attempt shell execution",
            "triggers": ["hack system"],
            "steps": [{"type": "launch_app", "target": "powershell.exe", "args": ["-Command", "whoami"]}],
        },
    )
    assert is_err is True
    assert "error" in payload


def test_mcp_server_stdio_subprocess_end_to_end(tmp_path: Path):
    """Pipe initialize + tools/list + tools/call test_route into `python -m src.mcp_server`."""
    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["COMPUTER_AUTO_LEARNED_PATH"] = str(tmp_path / "sub_learned.json")
    env["COMPUTER_AUTO_HISTORY_PATH"] = str(tmp_path / "sub_history.jsonl")

    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "pytest"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "test_route", "arguments": {"utterance": "volume up"}},
        },
    ]
    stdin_payload = "\n".join(json.dumps(r) for r in requests) + "\n"

    proc = subprocess.run(
        [sys.executable, "-m", "src.mcp_server"],
        input=stdin_payload,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env=env,
        timeout=15,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 3

    r1 = json.loads(lines[0])
    r2 = json.loads(lines[1])
    r3 = json.loads(lines[2])

    assert r1["id"] == 1 and r1["result"]["serverInfo"]["name"] == "computer-auto"
    assert r2["id"] == 2 and len(r2["result"]["tools"]) >= 10
    assert r3["id"] == 3 and r3["result"]["isError"] is False
    route_info = json.loads(r3["result"]["content"][0]["text"])
    assert route_info["intent_name"] == "volume_up"
    assert route_info["tier"] == "keyword"
