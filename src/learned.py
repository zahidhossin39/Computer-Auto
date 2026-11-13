"""Persistent learned-command store, step validator, fuzzy matcher, and history auto-suggester.

Stores learned and suggested commands at ``%APPDATA%\\Computer-Auto\\learned_commands.json``
(or an override path via ``COMPUTER_AUTO_LEARNED_PATH`` / ``LEARNED_PATH``).
"""

from __future__ import annotations

from datetime import datetime, timezone
import difflib
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, List, Optional, Union
import uuid

from src.config import Intent, IntentAction, get_appdata_dir

LEARNED_PATH: Optional[Path] = None
_LOCK = threading.RLock()

ALLOWED_STEP_TYPES = {
    "launch_app",
    "open_app",
    "open_url",
    "hotkey",
    "type_text",
    "type_in_window",
    "focus_window",
    "minimize_window",
    "maximize_window",
    "restore_window",
    "close_window",
    "system_action",
    "search_in_browser",
    "say",
    "click_element",
    "wait",
}

FORBIDDEN_STEP_TYPES = {
    "shell",
    "exec",
    "eval",
    "cmd",
    "powershell",
    "pwsh",
    "bash",
    "sh",
    "script",
    "subprocess",
    "run_shell",
    "arbitrary_command",
    "click_pixel",
    "raw_click",
    "mouse_move",
}

FORBIDDEN_EXECUTABLES = {
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "bash",
    "bash.exe",
    "sh",
    "sh.exe",
    "wsl",
    "wsl.exe",
    "wscript",
    "wscript.exe",
    "cscript",
    "cscript.exe",
    "mshta",
    "mshta.exe",
    "rundll32",
    "rundll32.exe",
    "regsvr32",
    "regsvr32.exe",
}

FORBIDDEN_ARG_FLAGS = {
    "/c",
    "/k",
    "-c",
    "-command",
    "-enc",
    "-encodedcommand",
    "-e",
}

SHELL_META_RE = re.compile(r"(?:&&|\|\||[;|`]|[$]\()")

ALLOWED_SYSTEM_COMMANDS = {
    "volume_step_up",
    "volume_step_down",
    "volume_toggle_mute",
    "media_play_pause",
    "media_next",
    "media_previous",
    "window_snap_left",
    "window_snap_right",
    "window_minimize_active",
    "window_maximize_active",
    "window_restore_active",
    "window_close_active",
    "system_lock",
    "key_enter",
    "key_escape",
    "key_tab",
    "key_backspace",
    "key_delete",
    "key_page_down",
    "key_page_up",
}

POLITE_PREFIX_RE = re.compile(
    r"^(?:(?:please|okay|ok|hey|computer|nova|can you|could you|would you|will you|"
    r"i want to|i want you to|id like to|go ahead and|just)\s+)+",
    re.I,
)


def get_learned_path(path: Optional[Union[Path, str]] = None) -> Path:
    """Resolve the active learned_commands.json path."""
    if path is not None:
        return Path(path)
    if LEARNED_PATH is not None:
        return Path(LEARNED_PATH)
    env_override = os.environ.get("COMPUTER_AUTO_LEARNED_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return get_appdata_dir() / "learned_commands.json"


def normalize_phrase(text: str) -> str:
    """Normalize an utterance or trigger phrase for deterministic comparison."""
    cleaned = re.sub(r"[^\w\s]", "", str(text or "")).lower().strip()
    cleaned = POLITE_PREFIX_RE.sub("", cleaned).strip() or cleaned
    words = [w for w in cleaned.split() if w not in ("the", "a", "an")]
    return " ".join(words)


def _slugify_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", str(name or "").strip().lower()).strip("_")
    return slug or f"learned_{uuid.uuid4().hex[:6]}"


def _check_no_shell_injection(value: Optional[str], field_name: str) -> None:
    if not value:
        return
    s = str(value).strip()
    if SHELL_META_RE.search(s):
        raise ValueError(f"Forbidden shell metacharacters in {field_name}: {s!r}")


def validate_step(step: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a single command step.

    Raises ValueError if the step uses an unknown type, attempts shell/command execution,
    or uses raw pixel coordinates instead of UIA identifiers for click_element.
    """
    if not isinstance(step, dict):
        raise ValueError("Each command step must be a JSON object (dict).")

    step_type = str(step.get("type") or "").strip().lower()
    if not step_type:
        raise ValueError("Step is missing required 'type' field.")
    if step_type in FORBIDDEN_STEP_TYPES or step_type not in ALLOWED_STEP_TYPES:
        raise ValueError(
            f"Unsupported or forbidden step type {step_type!r}. "
            f"Allowed types: {sorted(ALLOWED_STEP_TYPES)}"
        )

    command = step.get("command")
    target = step.get("target")
    fallback_target = step.get("fallback_target")
    raw_args = step.get("args") or []
    raw_keys = step.get("keys") or []

    if not isinstance(raw_args, list):
        raise ValueError("Step 'args' must be a list of strings.")
    if not isinstance(raw_keys, list):
        raise ValueError("Step 'keys' must be a list of key names.")

    args = [str(a) for a in raw_args if a is not None]
    keys = [str(k).strip().lower() for k in raw_keys if k is not None and str(k).strip()]

    # Reject raw pixel coordinates on click_element (or any step)
    if step_type == "click_element":
        if any(coord_key in step for coord_key in ("x", "y", "coords", "coordinates", "pixel", "pixels")):
            raise ValueError(
                "click_element requires a UIA element name or automation_id, NOT raw pixel coordinates (x/y)."
            )
        el_name = (
            target
            or step.get("name")
            or step.get("element")
            or step.get("automation_id")
            or command
        )
        if not el_name or not str(el_name).strip():
            raise ValueError("click_element requires a non-empty UIA element 'target' (or 'name'/'automation_id').")
        target = str(el_name).strip()
        if step.get("automation_id") and not command:
            command = str(step["automation_id"]).strip()

    elif step_type in ("launch_app", "open_app"):
        app_target = str(target or command or "").strip()
        if not app_target:
            raise ValueError(f"{step_type} requires a 'target' application or executable name.")
        exe_base = os.path.basename(app_target.replace("\\", "/")).lower().strip()
        if exe_base in FORBIDDEN_EXECUTABLES or app_target.lower() in FORBIDDEN_EXECUTABLES:
            raise ValueError(f"Launching shell/interpreter {app_target!r} is forbidden.")
        _check_no_shell_injection(app_target, "target")
        _check_no_shell_injection(str(command or ""), "command")
        for arg in args:
            if arg.strip().lower() in FORBIDDEN_ARG_FLAGS:
                raise ValueError(f"Forbidden shell execution flag {arg!r} in args.")
            _check_no_shell_injection(arg, "args")
        target = app_target

    elif step_type == "open_url":
        url = str(target or step.get("url") or command or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"open_url target must start with http:// or https:// (got {url!r}).")
        target = url

    elif step_type == "hotkey":
        if not keys:
            raise ValueError("hotkey step requires a non-empty 'keys' list (e.g. ['ctrl', 't']).")

    elif step_type in ("type_text", "type_in_window", "search_in_browser", "say"):
        txt = target if target is not None else step.get("text")
        if txt is None or not str(txt).strip():
            raise ValueError(f"{step_type} requires non-empty 'target' (or 'text').")
        target = str(txt)

    elif step_type in ("focus_window", "minimize_window", "maximize_window", "restore_window", "close_window"):
        win_target = str(target or command or "").strip()
        if not win_target:
            raise ValueError(f"{step_type} requires a window 'target' or 'command'.")
        target = win_target

    elif step_type == "system_action":
        sys_cmd = str(command or target or "").strip()
        if sys_cmd not in ALLOWED_SYSTEM_COMMANDS:
            raise ValueError(
                f"Unknown system_action command {sys_cmd!r}. "
                f"Allowed: {sorted(ALLOWED_SYSTEM_COMMANDS)}"
            )
        command = sys_cmd

    elif step_type == "wait":
        wait_val = step.get("wait_ms") or step.get("ms") or command or target or 500
        try:
            wait_ms = max(0, min(30000, int(float(wait_val))))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid wait duration: {wait_val!r}") from exc
        command = str(wait_ms)
        target = str(wait_ms)

    normalized: Dict[str, Any] = {"type": step_type}
    if command is not None:
        normalized["command"] = str(command)
    if target is not None:
        normalized["target"] = str(target)
    if fallback_target is not None:
        normalized["fallback_target"] = str(fallback_target)
    if args:
        normalized["args"] = args
    if keys:
        normalized["keys"] = keys
    return normalized


def validate_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate a non-empty list of command steps."""
    if not isinstance(steps, list) or len(steps) == 0:
        raise ValueError("A learned command must contain at least one step.")
    return [validate_step(s) for s in steps]


def _load_store(path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    target = get_learned_path(path)
    with _LOCK:
        if not target.is_file():
            return []
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("commands"), list):
                return [c for c in raw["commands"] if isinstance(c, dict)]
            if isinstance(raw, list):
                return [c for c in raw if isinstance(c, dict)]
        except Exception:
            return []
    return []


def _save_store(commands: List[Dict[str, Any]], path: Optional[Union[Path, str]] = None) -> None:
    target = get_learned_path(path)
    payload = json.dumps(commands, indent=2, ensure_ascii=False)
    with _LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(target)


def list_commands(
    include_disabled: bool = True,
    *,
    path: Optional[Union[Path, str]] = None,
) -> List[Dict[str, Any]]:
    """Return all stored learned/suggested commands."""
    cmds = _load_store(path)
    if include_disabled:
        return cmds
    return [c for c in cmds if bool(c.get("enabled", True))]


def add_command(
    name: str,
    description: str,
    triggers: List[str],
    steps: List[Dict[str, Any]],
    source_event_ids: Optional[List[str]] = None,
    enabled: bool = True,
    *,
    suggested: bool = False,
    cmd_id: Optional[str] = None,
    path: Optional[Union[Path, str]] = None,
) -> Dict[str, Any]:
    """Validate and persist a new learned command (or update if same name/id exists)."""
    if not isinstance(triggers, list) or not any(str(t).strip() for t in triggers):
        raise ValueError("triggers must be a non-empty list of spoken phrases.")
    clean_triggers: List[str] = []
    seen_t: set[str] = set()
    for t in triggers:
        s = str(t or "").strip().lower()
        if s and s not in seen_t:
            seen_t.add(s)
            clean_triggers.append(s)

    validated_steps = validate_steps(steps)
    slug = _slugify_name(name)

    with _LOCK:
        cmds = _load_store(path)
        for existing in cmds:
            if (cmd_id and existing.get("id") == cmd_id) or existing.get("name") == slug:
                existing["name"] = slug
                existing["description"] = str(description or slug).strip()
                existing["triggers"] = clean_triggers
                existing["steps"] = validated_steps
                if source_event_ids is not None:
                    existing["source_event_ids"] = [str(x) for x in source_event_ids]
                existing["enabled"] = bool(enabled)
                existing["suggested"] = bool(suggested and not enabled)
                _save_store(cmds, path)
                return dict(existing)

        record: Dict[str, Any] = {
            "id": str(cmd_id or f"cmd_{uuid.uuid4().hex[:10]}"),
            "name": slug,
            "description": str(description or slug).strip(),
            "triggers": clean_triggers,
            "steps": validated_steps,
            "source_event_ids": [str(x) for x in (source_event_ids or [])],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "uses": 0,
            "enabled": bool(enabled),
            "suggested": bool(suggested and not enabled),
        }
        cmds.append(record)
        _save_store(cmds, path)
        return dict(record)


def update_command(
    cmd_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    triggers: Optional[List[str]] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
    enabled: Optional[bool] = None,
    suggested: Optional[bool] = None,
    source_event_ids: Optional[List[str]] = None,
    uses: Optional[int] = None,
    path: Optional[Union[Path, str]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Update an existing learned command by id (or name)."""
    target_id = str(cmd_id or "").strip()
    if not target_id:
        raise ValueError("cmd_id is required.")

    with _LOCK:
        cmds = _load_store(path)
        for cmd in cmds:
            if cmd.get("id") == target_id or cmd.get("name") == target_id:
                if name is not None:
                    cmd["name"] = _slugify_name(name)
                if description is not None:
                    cmd["description"] = str(description).strip()
                if triggers is not None:
                    if not isinstance(triggers, list) or not any(str(t).strip() for t in triggers):
                        raise ValueError("triggers must be a non-empty list of strings.")
                    cmd["triggers"] = [str(t).strip().lower() for t in triggers if str(t).strip()]
                if steps is not None:
                    cmd["steps"] = validate_steps(steps)
                if enabled is not None:
                    cmd["enabled"] = bool(enabled)
                    if enabled:
                        cmd["suggested"] = False
                if suggested is not None:
                    cmd["suggested"] = bool(suggested)
                if source_event_ids is not None:
                    cmd["source_event_ids"] = [str(x) for x in source_event_ids]
                if uses is not None:
                    cmd["uses"] = max(0, int(uses))
                for k, v in extra.items():
                    if k in ("description", "enabled", "suggested") and v is not None:
                        cmd[k] = v
                _save_store(cmds, path)
                return dict(cmd)

    raise KeyError(f"Learned command not found: {target_id!r}")


def delete_command(cmd_id: str, *, path: Optional[Union[Path, str]] = None) -> bool:
    """Delete a learned command by id (or name). Returns True if removed."""
    target_id = str(cmd_id or "").strip()
    if not target_id:
        return False
    with _LOCK:
        cmds = _load_store(path)
        kept = [c for c in cmds if c.get("id") != target_id and c.get("name") != target_id]
        if len(kept) == len(cmds):
            return False
        _save_store(kept, path)
        return True


def approve_suggestion(cmd_id: str, *, path: Optional[Union[Path, str]] = None) -> Dict[str, Any]:
    """Approve a suggested command so it becomes enabled for live routing."""
    return update_command(cmd_id, enabled=True, suggested=False, path=path)


def match(
    utterance: str,
    *,
    path: Optional[Union[Path, str]] = None,
    increment_uses: bool = True,
) -> Optional[Dict[str, Any]]:
    """Match an utterance against enabled learned commands (exact + fuzzy trigger match)."""
    norm_u = normalize_phrase(utterance)
    if not norm_u:
        return None

    with _LOCK:
        cmds = _load_store(path)
        enabled_cmds = [c for c in cmds if bool(c.get("enabled", True))]
        if not enabled_cmds:
            return None

        # 1. Exact normalized trigger match
        for cmd in enabled_cmds:
            for trig in cmd.get("triggers", []):
                if normalize_phrase(trig) == norm_u:
                    if increment_uses:
                        cmd["uses"] = int(cmd.get("uses", 0)) + 1
                        _save_store(cmds, path)
                    return dict(cmd)

        # 2. Containment match (multi-word trigger contained with <= 2 extra words)
        best_contain: Optional[tuple[int, Dict[str, Any]]] = None
        for cmd in enabled_cmds:
            for trig in cmd.get("triggers", []):
                norm_t = normalize_phrase(trig)
                if not norm_t or " " not in norm_t:
                    continue
                pattern = r"\b" + re.escape(norm_t) + r"\b"
                if re.search(pattern, norm_u):
                    remainder = re.sub(pattern, " ", norm_u, count=1).split()
                    if len(remainder) <= 2:
                        score = len(norm_t)
                        if best_contain is None or score > best_contain[0]:
                            best_contain = (score, cmd)
        if best_contain is not None:
            matched_cmd = best_contain[1]
            if increment_uses:
                matched_cmd["uses"] = int(matched_cmd.get("uses", 0)) + 1
                _save_store(cmds, path)
            return dict(matched_cmd)

        # 3. Fuzzy similarity match (token overlap + SequenceMatcher ratio >= 0.84)
        u_words = set(norm_u.split())
        best_fuzzy: Optional[tuple[float, Dict[str, Any]]] = None
        for cmd in enabled_cmds:
            for trig in cmd.get("triggers", []):
                norm_t = normalize_phrase(trig)
                if not norm_t:
                    continue
                t_words = set(norm_t.split())
                # Do not fuzzy-match if numbers/ordinals differ (e.g. "profile 1" vs "profile 2")
                u_nums = {w for w in u_words if any(ch.isdigit() for ch in w)}
                t_nums = {w for w in t_words if any(ch.isdigit() for ch in w)}
                if u_nums != t_nums:
                    continue
                seq_ratio = difflib.SequenceMatcher(None, norm_u, norm_t).ratio()
                jaccard = len(u_words & t_words) / max(1, len(u_words | t_words))
                combined = 0.6 * seq_ratio + 0.4 * jaccard
                if seq_ratio >= 0.84 and combined >= 0.78:
                    if best_fuzzy is None or combined > best_fuzzy[0]:
                        best_fuzzy = (combined, cmd)

        if best_fuzzy is not None:
            matched_cmd = best_fuzzy[1]
            if increment_uses:
                matched_cmd["uses"] = int(matched_cmd.get("uses", 0)) + 1
                _save_store(cmds, path)
            return dict(matched_cmd)

    return None


def _step_to_intent_action(step: Dict[str, Any]) -> IntentAction:
    """Convert a validated step dict into an IntentAction dataclass."""
    return IntentAction(
        type=str(step.get("type") or "system_action"),
        command=step.get("command"),
        keys=list(step.get("keys") or []),
        target=step.get("target"),
        fallback_target=step.get("fallback_target"),
        args=list(step.get("args") or []),
    )


def to_intent(cmd: Dict[str, Any]) -> Intent:
    """Convert a learned command dictionary into a router Intent."""
    raw_steps = cmd.get("steps") or []
    validated = validate_steps(raw_steps)
    step_actions = [_step_to_intent_action(s) for s in validated]
    primary_action = step_actions[0]
    intent = Intent(
        name=str(cmd.get("name") or cmd.get("id") or "learned_command"),
        category="learned",
        triggers=[str(t).lower().strip() for t in cmd.get("triggers", []) if str(t).strip()],
        action=primary_action,
        is_destructive=bool(cmd.get("is_destructive", False)),
    )
    # Attach full step sequence and metadata for multi-step execution & inspection
    setattr(intent, "steps", step_actions)
    setattr(intent, "learned_id", cmd.get("id"))
    setattr(intent, "description", cmd.get("description", ""))
    return intent


def execute_learned_action(action: IntentAction, executor: Optional[Any] = None) -> bool:
    """Execute a learned IntentAction, including 'click_element' (via UIA) and 'wait'."""
    if action.type == "wait":
        ms_str = action.command or action.target or "500"
        try:
            sec = max(0.0, min(30.0, float(ms_str) / 1000.0 if float(ms_str) > 30 else float(ms_str)))
        except (TypeError, ValueError):
            sec = 0.5
        time.sleep(sec)
        return True

    if action.type == "click_element":
        target_name = str(action.target or action.command or "").strip().lower()
        if not target_name:
            return False
        try:
            from src.vision import uia
            import pyautogui

            hwnd = executor._get_active_window() if executor and hasattr(executor, "_get_active_window") else 0
            elements = uia.list_elements(hwnd or 0)
            for el in elements:
                if target_name in el.name.lower() or el.name.lower() in target_name:
                    cx, cy = el.center
                    pyautogui.click(cx, cy)
                    return True
        except Exception:
            return False
        return False

    if executor is not None:
        if action.type == "system_action" and action.command:
            return bool(executor.execute_system_action(action.command))
        if action.type == "launch_app":
            return bool(executor.launch_app(action))
        return bool(executor.run_action(action))
    return False


def _install_executor_hook() -> None:
    """Extend WindowsExecutor.run_action so learned steps (click_element, wait, multi-step) execute natively."""
    try:
        from src.executor.windows import WindowsExecutor

        if getattr(WindowsExecutor, "_learned_hook_installed", False):
            return
        orig_run_action = WindowsExecutor.run_action

        def _patched_run_action(self: Any, action: IntentAction) -> bool:
            if action.type in ("click_element", "wait"):
                return execute_learned_action(action, executor=self)
            return orig_run_action(self, action)

        WindowsExecutor.run_action = _patched_run_action  # type: ignore[method-assign]
        WindowsExecutor._learned_hook_installed = True  # type: ignore[attr-defined]
    except Exception:
        pass


_install_executor_hook()


def _vision_actions_to_steps(actions: List[Dict[str, Any]], utterance: str) -> List[Dict[str, Any]]:
    """Convert recorded history actions from Vision runs into safe deterministic steps."""
    steps: List[Dict[str, Any]] = []
    for raw in actions or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("type") or raw.get("action") or "").strip().lower()
        if kind in ("done", "none", ""):
            continue
        if kind == "hotkey":
            keys = [str(k).strip().lower() for k in (raw.get("keys") or []) if str(k).strip()]
            if keys:
                steps.append({"type": "hotkey", "keys": keys})
        elif kind in ("type", "type_text"):
            txt = str(raw.get("target") or raw.get("text") or "").strip()
            if txt:
                steps.append({"type": "type_text", "target": txt})
        elif kind == "wait":
            wait_ms = raw.get("wait_ms") or raw.get("command") or "500"
            steps.append({"type": "wait", "command": str(wait_ms), "target": str(wait_ms)})
        elif kind in ("click", "double_click", "right_click", "click_element"):
            el_target = (
                raw.get("target")
                or raw.get("element")
                or raw.get("name")
                or raw.get("automation_id")
            )
            if not el_target and raw.get("explanation"):
                exp = str(raw["explanation"]).strip()
                quoted = re.findall(r"['\"]([^'\"]{2,60})['\"]", exp)
                el_target = quoted[0] if quoted else exp[:60]
            if not el_target:
                el_target = utterance.strip()[:60]
            step_dict: Dict[str, Any] = {"type": "click_element", "target": str(el_target).strip()}
            if raw.get("automation_id"):
                step_dict["command"] = str(raw["automation_id"]).strip()
            steps.append(step_dict)
        elif kind in ALLOWED_STEP_TYPES:
            candidate = {k: v for k, v in raw.items() if k not in ("x", "y", "coords", "coordinates", "pixel", "pixels")}
            candidate["type"] = kind
            try:
                steps.append(validate_step(candidate))
            except ValueError:
                pass

    if not steps:
        # Synthesize a safe UIA element click step from the utterance if raw actions were empty
        clean_target = utterance.strip()[:60] or "Active Element"
        steps.append({"type": "click_element", "target": clean_target})

    return validate_steps(steps)


def suggest_from_history(
    events: Optional[List[Dict[str, Any]]] = None,
    *,
    min_occurrences: int = 2,
    persist: bool = True,
    path: Optional[Union[Path, str]] = None,
) -> List[Dict[str, Any]]:
    """Analyze execution history and propose learned commands for repeated successful tasks.

    Finds repeated utterances (especially Vision tasks succeeding >= ``min_occurrences`` times)
    and stores proposals with ``enabled=False, suggested=True`` so nothing runs unapproved.
    """
    if events is None:
        from src import history
        events = history.read_events(limit=500)

    # Group successful events by normalized utterance
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        if not bool(ev.get("success", False)):
            continue
        utt = str(ev.get("utterance") or "").strip()
        norm = normalize_phrase(utt)
        if not norm:
            continue
        route = str(ev.get("route") or "").strip().lower()
        # Focus on vision tasks (or repeated utterances that have action traces)
        if route == "vision" or ev.get("actions"):
            groups.setdefault(norm, []).append(ev)

    existing_cmds = _load_store(path)
    existing_by_trigger: Dict[str, Dict[str, Any]] = {}
    for cmd in existing_cmds:
        for trig in cmd.get("triggers", []):
            existing_by_trigger[normalize_phrase(trig)] = cmd

    proposals: List[Dict[str, Any]] = []
    for norm_utt, group in groups.items():
        if len(group) < max(1, min_occurrences):
            continue

        if norm_utt in existing_by_trigger:
            existing = existing_by_trigger[norm_utt]
            if not existing.get("enabled", True):
                proposals.append(dict(existing))
            continue

        # Pick the most recent event with actions to derive the step sequence
        chosen_ev = group[-1]
        for candidate_ev in reversed(group):
            if candidate_ev.get("actions"):
                chosen_ev = candidate_ev
                break

        raw_utterance = str(chosen_ev.get("utterance") or norm_utt).strip()
        try:
            steps = _vision_actions_to_steps(chosen_ev.get("actions") or [], raw_utterance)
        except ValueError:
            continue

        # Collect distinct raw utterances in this group as triggers
        triggers: List[str] = []
        for ev in group:
            u = str(ev.get("utterance") or "").strip().lower()
            if u and u not in triggers:
                triggers.append(u)
        if norm_utt not in triggers:
            triggers.append(norm_utt)

        source_ids = [str(ev.get("id")) for ev in group if ev.get("id")]
        slug_words = norm_utt.split()[:4]
        cmd_name = _slugify_name("learned_" + "_".join(slug_words))
        desc = f"Auto-suggested from {len(group)} successful runs of '{raw_utterance}'"

        if persist:
            saved = add_command(
                name=cmd_name,
                description=desc,
                triggers=triggers,
                steps=steps,
                source_event_ids=source_ids,
                enabled=False,
                suggested=True,
                path=path,
            )
            proposals.append(saved)
        else:
            proposals.append({
                "id": f"cmd_{uuid.uuid4().hex[:10]}",
                "name": cmd_name,
                "description": desc,
                "triggers": triggers,
                "steps": steps,
                "source_event_ids": source_ids,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "uses": 0,
                "enabled": False,
                "suggested": True,
            })

    return proposals


def get_mcp_config_snippet(repo_dir: Optional[Union[Path, str]] = None) -> str:
    """Return the copyable JSON config snippet for Claude Desktop / Cursor / MCP clients."""
    if repo_dir is not None:
        cwd = str(Path(repo_dir))
    else:
        default_repo = Path(r"D:\Vibe-coding\Computer-Auto")
        if default_repo.exists():
            cwd = str(default_repo)
        else:
            cwd = str(Path(__file__).resolve().parent.parent)
    snippet = {
        "mcpServers": {
            "computer-auto": {
                "command": "python",
                "args": ["-m", "src.mcp_server"],
                "cwd": cwd,
            }
        }
    }
    return json.dumps(snippet, indent=2)


# Thin bridge helper functions for src/bridge.py
def bridge_list_learned(*, path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Run auto-suggestion from history and return all learned + suggested commands."""
    try:
        suggest_from_history(path=path)
    except Exception:
        pass
    return list_commands(include_disabled=True, path=path)


def bridge_approve_learned(cmd_id: str, *, path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Approve a suggested command by id and return the updated command list."""
    try:
        approve_suggestion(cmd_id, path=path)
    except Exception:
        pass
    return list_commands(include_disabled=True, path=path)


def bridge_toggle_learned(
    cmd_id: str,
    enabled: bool,
    *,
    path: Optional[Union[Path, str]] = None,
) -> List[Dict[str, Any]]:
    """Toggle a learned command's enabled flag and return the updated command list."""
    try:
        update_command(cmd_id, enabled=bool(enabled), path=path)
    except Exception:
        pass
    return list_commands(include_disabled=True, path=path)


def bridge_delete_learned(cmd_id: str, *, path: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    """Delete a learned command by id and return the updated command list."""
    try:
        delete_command(cmd_id, path=path)
    except Exception:
        pass
    return list_commands(include_disabled=True, path=path)
