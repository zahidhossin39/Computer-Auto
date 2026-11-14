"""Model Context Protocol (MCP) stdio server for Computer-Auto.

Run with:
    python -m src.mcp_server

Exposes Computer-Auto's execution history, Vision task traces, built-in intents,
learned command palette, auto-suggester, and dry-run router tester over stdio so
external AI agents (Claude Desktop, Cursor, Windsurf, etc.) can continuously analyze
what the user asks for and convert slow Vision tasks into instant deterministic commands.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional, TextIO

if __package__ is None or __package__ == "":
    _REPO_ROOT = str(Path(__file__).resolve().parent.parent)
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

from src import history, learned
from src.config import load_intents
from src.router.router import CommandRouter

SERVER_NAME = "computer-auto"
SERVER_VERSION = "2.5.1"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def tool_get_history(
    limit: int = 200,
    route: Optional[str] = None,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch recent command execution history from history.jsonl."""
    events = history.read_events(limit=int(limit or 200), route=route, since=since)
    return {"events": events, "count": len(events)}


def tool_get_vision_tasks(limit: int = 100) -> Dict[str, Any]:
    """Fetch recent tasks that fell back to the Tier-2 Vision model."""
    events = history.read_events(limit=int(limit or 100), route="vision")
    return {"events": events, "count": len(events)}


def tool_list_commands(include_disabled: bool = True) -> Dict[str, Any]:
    """List all learned and suggested commands in learned_commands.json."""
    cmds = learned.list_commands(include_disabled=bool(include_disabled))
    return {"commands": cmds, "count": len(cmds)}


def tool_list_builtin_intents() -> Dict[str, Any]:
    """List all static built-in intents from intents.yaml."""
    intents = load_intents()
    serialized: List[Dict[str, Any]] = []
    for item in intents:
        serialized.append({
            "name": item.name,
            "category": item.category,
            "triggers": list(item.triggers),
            "is_destructive": bool(item.is_destructive),
            "action": {
                "type": item.action.type,
                "command": item.action.command,
                "target": item.action.target,
                "fallback_target": item.action.fallback_target,
                "keys": list(item.action.keys or []),
                "args": list(item.action.args or []),
            },
        })
    return {"intents": serialized, "count": len(serialized)}


def tool_suggest_commands(min_occurrences: int = 2) -> Dict[str, Any]:
    """Analyze history for repeated Vision tasks and store/return suggested command proposals."""
    proposals = learned.suggest_from_history(min_occurrences=max(1, int(min_occurrences or 2)))
    return {"suggestions": proposals, "count": len(proposals)}


def tool_create_command(
    name: str,
    description: str,
    triggers: List[str],
    steps: List[Dict[str, Any]],
    enabled: bool = True,
    source_event_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create and persist a validated learned command in learned_commands.json."""
    cmd = learned.add_command(
        name=name,
        description=description,
        triggers=triggers,
        steps=steps,
        source_event_ids=source_event_ids,
        enabled=bool(enabled),
    )
    return {"command": cmd}


def tool_update_command(
    id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    triggers: Optional[List[str]] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
    enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """Update an existing learned or suggested command by id or name."""
    cmd = learned.update_command(
        id,
        name=name,
        description=description,
        triggers=triggers,
        steps=steps,
        enabled=enabled,
    )
    return {"command": cmd}


def tool_delete_command(id: str) -> Dict[str, Any]:
    """Delete a learned or suggested command by id or name."""
    removed = learned.delete_command(id)
    return {"deleted": bool(removed), "id": str(id)}


def tool_approve_suggestion(id: str) -> Dict[str, Any]:
    """Approve a suggested command (sets enabled=True, suggested=False)."""
    cmd = learned.approve_suggestion(id)
    return {"command": cmd}


def tool_test_route(utterance: str, use_jev: bool = False) -> Dict[str, Any]:
    """Dry-run CommandRouter.route(utterance) without executing anything on the OS."""
    intents = load_intents()
    router = CommandRouter(intents=intents, use_jev=bool(use_jev))
    # Do not increment 'uses' counter during dry-run route inspection
    orig_match = learned.match
    try:
        learned.match = lambda u, **kw: orig_match(u, increment_uses=False, **kw)  # type: ignore[assignment]
        res = router.route(str(utterance or ""))
    finally:
        learned.match = orig_match  # type: ignore[assignment]

    tier = getattr(res, "route", "vision" if res.is_vision else "keyword")
    action_dict: Optional[Dict[str, Any]] = None
    steps_list: Optional[List[Dict[str, Any]]] = None
    if res.intent and res.intent.action:
        act = res.intent.action
        action_dict = {
            "type": act.type,
            "command": act.command,
            "target": act.target,
            "fallback_target": act.fallback_target,
            "keys": list(act.keys or []),
            "args": list(act.args or []),
        }
        raw_steps = getattr(res.intent, "steps", None)
        if raw_steps:
            steps_list = [
                {
                    "type": s.type,
                    "command": s.command,
                    "target": s.target,
                    "keys": list(s.keys or []),
                    "args": list(s.args or []),
                }
                for s in raw_steps
            ]

    return {
        "utterance": str(utterance or ""),
        "tier": tier,
        "route": tier,
        "is_vision": bool(res.is_vision),
        "intent_name": res.intent.name if res.intent else None,
        "category": res.intent.category if res.intent else None,
        "action": action_dict,
        "steps": steps_list,
    }


# ---------------------------------------------------------------------------
# Tool catalog with agent-oriented instructions for turning history -> commands
# ---------------------------------------------------------------------------

STEP_SCHEMA_DOCS = (
    "Each step in `steps` must be an object with `type` in:\n"
    "- `launch_app`: `{\"type\": \"launch_app\", \"target\": \"notepad.exe\", \"args\": [\"...\"]}`\n"
    "- `open_app`: `{\"type\": \"open_app\", \"target\": \"<AppID/exe>\", \"command\": \"<App Name>\"}`\n"
    "- `open_url`: `{\"type\": \"open_url\", \"target\": \"https://...\"}` (must be http/https)\n"
    "- `hotkey`: `{\"type\": \"hotkey\", \"keys\": [\"ctrl\", \"shift\", \"n\"]}`\n"
    "- `type_text`: `{\"type\": \"type_text\", \"target\": \"text to type\"}`\n"
    "- `focus_window`: `{\"type\": \"focus_window\", \"target\": \"<window title or hwnd>\"}`\n"
    "- `system_action`: `{\"type\": \"system_action\", \"command\": \"volume_step_up|volume_step_down|volume_toggle_mute|media_play_pause|media_next|media_previous|window_snap_left|window_snap_right|window_minimize_active|window_maximize_active|window_restore_active|window_close_active|system_lock|key_enter|key_escape|key_tab|key_backspace|key_delete|key_page_down|key_page_up\"}`\n"
    "- `search_in_browser`: `{\"type\": \"search_in_browser\", \"target\": \"query\"}`\n"
    "- `click_element`: `{\"type\": \"click_element\", \"target\": \"<UIA element name>\", \"command\": \"<optional automation_id>\"}` (NEVER pass raw pixel x/y coordinates; always use Windows UI Automation element names)\n"
    "- `wait`: `{\"type\": \"wait\", \"command\": \"500\"}` (milliseconds)\n"
    "Shell commands (cmd, powershell, bash) and raw pixel clicks are strictly rejected."
)

TOOLS_SPEC: List[Dict[str, Any]] = [
    {
        "name": "get_history",
        "description": (
            "Read Computer-Auto's execution history log (`history.jsonl`). "
            "Use this to inspect what the user asked (`utterance`), which routing tier handled it "
            "(`keyword`, `slot`, `jev`, `learned`, or `vision`), the UI actions performed (`actions`), "
            "and how long it took (`duration_ms`). Filter with `route='vision'` to find slow Vision "
            "tasks that can be converted into instant deterministic commands with `create_command`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 200, "description": "Maximum number of recent events to return."},
                "route": {
                    "type": "string",
                    "enum": ["keyword", "slot", "jev", "learned", "vision"],
                    "description": "Optional route tier filter.",
                },
                "since": {"type": "string", "description": "Optional ISO-8601 timestamp lower bound."},
            },
        },
    },
    {
        "name": "get_vision_tasks",
        "description": (
            "Fetch recent commands that fell back to the slow Tier-2 Vision model (`route='vision'`), "
            "including their full step-by-step action trace. Analyze these traces to synthesize "
            "reusable commands via `create_command` so similar future phrases execute in <10ms."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 100, "description": "Maximum number of Vision events to return."},
            },
        },
    },
    {
        "name": "list_commands",
        "description": (
            "List all learned and suggested commands in Computer-Auto's command palette (`learned_commands.json`), "
            "including triggers, steps, usage count, and whether each command is enabled or awaiting approval."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_disabled": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "list_builtin_intents",
        "description": (
            "List all built-in deterministic intents from `intents.yaml` (`name`, `category`, `triggers`, `action`). "
            "Check this before creating a command to avoid duplicating existing triggers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "suggest_commands",
        "description": (
            "Run the built-in pattern analyzer across `history.jsonl` to find repeated successful Vision tasks "
            "and generate unapproved command proposals (`enabled=false, suggested=true`). "
            "Review returned proposals and call `approve_suggestion(id)` or `update_command(id, ...)` to enable them."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_occurrences": {
                    "type": "integer",
                    "default": 2,
                    "description": "Minimum times a normalized utterance must succeed via Vision to be suggested.",
                },
            },
        },
    },
    {
        "name": "create_command",
        "description": (
            "Create a new deterministic learned command in Computer-Auto's command palette. "
            "Provide natural spoken `triggers` (including common paraphrases) and a sequence of safe deterministic `steps`. "
            + STEP_SCHEMA_DOCS
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Unique snake_case command identifier."},
                "description": {"type": "string", "description": "Human-readable summary of what the command does."},
                "triggers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Spoken/typed trigger phrases that should invoke this command.",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Ordered list of deterministic action steps.",
                },
                "enabled": {"type": "boolean", "default": True},
                "source_event_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional history event IDs this command was learned from.",
                },
            },
            "required": ["name", "description", "triggers", "steps"],
        },
    },
    {
        "name": "update_command",
        "description": (
            "Update an existing learned or suggested command's name, description, triggers, steps, or enabled state. "
            + STEP_SCHEMA_DOCS
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Command ID or name to update."},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "triggers": {"type": "array", "items": {"type": "string"}},
                "steps": {"type": "array", "items": {"type": "object"}},
                "enabled": {"type": "boolean"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "delete_command",
        "description": "Delete a learned or suggested command by its ID or name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Command ID or name to delete."},
            },
            "required": ["id"],
        },
    },
    {
        "name": "approve_suggestion",
        "description": "Approve a suggested command by ID (`enabled=true, suggested=false`) so the router immediately uses it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Suggested command ID or name to approve."},
            },
            "required": ["id"],
        },
    },
    {
        "name": "test_route",
        "description": (
            "Dry-run `CommandRouter.route(utterance)` without executing any desktop actions. "
            "Returns which routing tier (`keyword`, `learned`, `slot`, `jev`, or `vision`) and intent "
            "would handle the phrase. Always call `test_route` after creating or updating a command "
            "to confirm the user's phrasing hits the `learned` tier instead of `vision`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "utterance": {"type": "string", "description": "Spoken or typed phrase to test against the router."},
                "use_jev": {"type": "boolean", "default": False},
            },
            "required": ["utterance"],
        },
    },
]

TOOL_HANDLERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "get_history": tool_get_history,
    "get_vision_tasks": tool_get_vision_tasks,
    "list_commands": tool_list_commands,
    "list_builtin_intents": tool_list_builtin_intents,
    "suggest_commands": tool_suggest_commands,
    "create_command": tool_create_command,
    "update_command": tool_update_command,
    "delete_command": tool_delete_command,
    "approve_suggestion": tool_approve_suggestion,
    "test_route": tool_test_route,
}


# Optional registration with official `mcp` Python SDK if imported by external callers
try:
    from mcp.server.fastmcp import FastMCP

    mcp_app: Optional[Any] = FastMCP(SERVER_NAME)
    for _spec in TOOLS_SPEC:
        _fn = TOOL_HANDLERS[_spec["name"]]
        mcp_app.tool(name=_spec["name"], description=_spec["description"])(_fn)
except Exception:
    mcp_app = None


def handle_jsonrpc_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process one JSON-RPC 2.0 MCP request or notification.

    Returns a JSON-RPC 2.0 response dict for requests (messages with an ``id``),
    or ``None`` for notifications (messages without an ``id``).
    """
    method = str(msg.get("method") or "").strip()
    has_id = "id" in msg
    req_id = msg.get("id")
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    if not has_id:
        # Notification (e.g. notifications/initialized, notifications/cancelled) -> no response
        return None

    if method == "initialize":
        client_proto = str(params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_proto,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": TOOLS_SPEC,
            },
        }

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "resources": [
                    {
                        "uri": "computer-auto://history",
                        "name": "Execution History Log",
                        "description": "Recent voice and vision command execution events from history.jsonl",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "computer-auto://learned-commands",
                        "name": "Learned Commands Palette",
                        "description": "Learned and suggested commands stored in learned_commands.json",
                        "mimeType": "application/json",
                    },
                ]
            },
        }

    if method == "resources/read":
        uri = str(params.get("uri") or "")
        if uri == "computer-auto://history":
            data_text = json.dumps(tool_get_history(limit=200), ensure_ascii=False, indent=2)
        elif uri == "computer-auto://learned-commands":
            data_text = json.dumps(tool_list_commands(include_disabled=True), ensure_ascii=False, indent=2)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Unknown resource URI: {uri!r}"},
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "contents": [
                    {"uri": uri, "mimeType": "application/json", "text": data_text}
                ]
            },
        }

    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}}

    if method == "tools/call":
        tool_name = str(params.get("name") or "").strip()
        raw_args = params.get("arguments") or {}
        if not isinstance(raw_args, dict):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": "Tool arguments must be a JSON object."},
            }
        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name!r}"},
            }
        try:
            output = handler(**raw_args)
            text_payload = json.dumps(output, ensure_ascii=False)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text_payload}],
                    "structuredContent": output,
                    "isError": False,
                },
            }
        except Exception as exc:
            err_payload = {"error": str(exc), "tool": tool_name}
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(err_payload, ensure_ascii=False)}],
                    "structuredContent": err_payload,
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method!r}"},
    }


def serve_stdio(
    in_stream: Optional[TextIO] = None,
    out_stream: Optional[TextIO] = None,
) -> None:
    """Run the JSON-RPC 2.0 MCP server over stdio (newline-delimited JSON)."""
    reader = in_stream or sys.stdin
    writer = out_stream or sys.stdout

    for raw_line in reader:
        line = raw_line.strip()
        if not line:
            continue
        # Ignore HTTP-style Content-Length headers if a client sends LSP framing
        if line.lower().startswith("content-length:"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
            writer.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
            writer.flush()
            continue

        if isinstance(parsed, list):
            responses = []
            for item in parsed:
                if isinstance(item, dict):
                    resp = handle_jsonrpc_message(item)
                    if resp is not None:
                        responses.append(resp)
            if responses:
                writer.write(json.dumps(responses, ensure_ascii=False) + "\n")
                writer.flush()
        elif isinstance(parsed, dict):
            resp = handle_jsonrpc_message(parsed)
            if resp is not None:
                writer.write(json.dumps(resp, ensure_ascii=False) + "\n")
                writer.flush()


def main() -> None:
    """Entrypoint for `python -m src.mcp_server`. Routes all stray prints to stderr."""
    if sys.platform == "win32":
        for sname in ("stdin", "stdout", "stderr"):
            s = getattr(sys, sname, None)
            if s is not None and hasattr(s, "reconfigure"):
                try:
                    s.reconfigure(encoding="utf-8")
                except Exception:
                    pass

    protocol_out = sys.stdout
    sys.stdout = sys.stderr
    try:
        serve_stdio(in_stream=sys.stdin, out_stream=protocol_out)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
