"""Append-only JSON-Lines execution history log for Computer-Auto.

Stores every executed voice/typed command at ``%APPDATA%\\Computer-Auto\\history.jsonl``
(or an override path via ``COMPUTER_AUTO_HISTORY_PATH`` / ``HISTORY_PATH``) so both
the built-in pattern learner and external MCP agents can inspect past actions and
convert repeated Vision workflows into fast deterministic commands.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Union
import uuid

from src.config import get_appdata_dir

VALID_ROUTES = {"keyword", "slot", "jev", "learned", "vision"}
ROUTE_ALIASES = {
    "containment": "keyword",
    "exact": "keyword",
    "tier1": "keyword",
    "tier2": "vision",
}

# Module-level override and size limits (adjustable in tests)
HISTORY_PATH: Optional[Path] = None
MAX_HISTORY_BYTES: int = 2 * 1024 * 1024  # 2 MiB cap
MAX_HISTORY_LINES: int = 2000

_LOCK = threading.RLock()


def get_history_path(path: Optional[Union[Path, str]] = None) -> Path:
    """Resolve the active history.jsonl file path."""
    if path is not None:
        return Path(path)
    if HISTORY_PATH is not None:
        return Path(HISTORY_PATH)
    env_override = os.environ.get("COMPUTER_AUTO_HISTORY_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return get_appdata_dir() / "history.jsonl"


def _normalize_route(route: str) -> str:
    raw = str(route or "").strip().lower()
    if raw in VALID_ROUTES:
        return raw
    if raw in ROUTE_ALIASES:
        return ROUTE_ALIASES[raw]
    return "keyword"


def _sanitize_actions(actions: Any) -> List[Dict[str, Any]]:
    if not isinstance(actions, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for item in actions:
        if isinstance(item, dict):
            try:
                # Ensure JSON serializability via round-trip fallback
                json.dumps(item)
                cleaned.append(dict(item))
            except (TypeError, ValueError):
                cleaned.append({k: str(v) for k, v in item.items()})
    return cleaned


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _rotate_if_needed(target: Path) -> None:
    """Cap the JSONL file size and line count by retaining the newest half of records."""
    try:
        if not target.is_file():
            return
        size = target.stat().st_size
        if size <= MAX_HISTORY_BYTES:
            return
        lines = [ln for ln in target.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        keep_count = max(1, min(len(lines) // 2, MAX_HISTORY_LINES // 2))
        kept = lines[-keep_count:]
        # Also trim further if still above MAX_HISTORY_BYTES
        while len(kept) > 1 and sum(len(x.encode("utf-8")) + 1 for x in kept) > MAX_HISTORY_BYTES:
            kept = kept[len(kept) // 2 :]
        tmp = target.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        tmp.replace(target)
    except Exception:
        pass


def record_event(
    utterance: str,
    route: str,
    intent_name: Optional[str],
    actions: List[Dict[str, Any]],
    success: bool,
    duration_ms: int,
    error: Optional[str] = None,
    *,
    path: Optional[Union[Path, str]] = None,
) -> None:
    """Append one command execution event to history.jsonl.

    Thread-safe and guaranteed never to raise into the caller.
    """
    try:
        try:
            dur = max(0, int(duration_ms))
        except (TypeError, ValueError):
            dur = 0

        event: Dict[str, Any] = {
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "utterance": str(utterance or "").strip(),
            "route": _normalize_route(route),
            "intent_name": str(intent_name).strip() if intent_name else None,
            "actions": _sanitize_actions(actions),
            "success": bool(success),
            "duration_ms": dur,
            "error": str(error).strip() if error else None,
        }
        line = json.dumps(event, ensure_ascii=False)
        target = get_history_path(path)
        with _LOCK:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            _rotate_if_needed(target)
    except Exception:
        # Never propagate logging errors into the voice automation daemon
        pass


def read_events(
    limit: int = 200,
    route: Optional[str] = None,
    since: Optional[str] = None,
    *,
    path: Optional[Union[Path, str]] = None,
) -> List[Dict[str, Any]]:
    """Read recorded execution events from history.jsonl.

    Args:
        limit: Maximum number of most-recent matching events to return.
        route: Optional filter by route tier (``keyword|slot|jev|learned|vision``).
        since: Optional ISO-8601 timestamp string; only events at or after ``since`` are returned.
        path: Optional explicit file path override.
    """
    if limit is not None and limit <= 0:
        return []
    target = get_history_path(path)
    try:
        with _LOCK:
            if not target.is_file():
                return []
            raw_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

    route_filter = str(route).strip().lower() if route else None
    since_dt = _parse_iso(since) if since else None
    since_str = str(since).strip() if since else None

    events: List[Dict[str, Any]] = []
    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue

        if route_filter and str(item.get("route") or "").lower() != route_filter:
            continue

        if since_str:
            ev_ts = str(item.get("ts") or "")
            ev_dt = _parse_iso(ev_ts)
            if since_dt is not None and ev_dt is not None:
                if ev_dt < since_dt:
                    continue
            elif ev_ts < since_str:
                continue

        events.append(item)

    if limit is not None and len(events) > limit:
        events = events[-limit:]
    return events


def clear_history(*, path: Optional[Union[Path, str]] = None) -> None:
    """Remove the history log file (primarily for tests)."""
    target = get_history_path(path)
    try:
        with _LOCK:
            if target.is_file():
                target.unlink()
    except Exception:
        pass
