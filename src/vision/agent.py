"""Tier 2 Vision Agent: a vision model on OpenRouter plans GUI actions from screenshots."""

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import io
import json
import os
import re
import time
from typing import List, Optional
from PIL import Image
import pyautogui
import requests

from src import jev
from src.executor.guardrail import SafetyGuardrail
from src.executor.windows import send_hotkey, type_text
from src.vision import uia

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_session = requests.Session()  # keep-alive across the 2+ calls per step
_pool = ThreadPoolExecutor(max_workers=4)  # a call Jev beat keeps running; don't let it block the next
# Tried in order when the chosen model's provider is rate-limited (429) or down
FALLBACK_MODELS = ["google/gemini-3.1-flash-lite", "qwen/qwen3-vl-30b-a3b-instruct"]


@dataclass
class VisionAction:
    action: str  # click, double_click, right_click, type, hotkey, scroll, wait, done, none
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    keys: List[str] = field(default_factory=list)
    submit: bool = False  # press Enter after typing
    final: bool = False  # this action alone finishes the request: no look afterwards
    direction: str = "down"  # for scroll
    explanation: str = ""


SYSTEM_PROMPT = """You are a desktop GUI automation agent working step by step.
You get the user request, the steps already taken, and a fresh screenshot of the screen.
Decide the ONE next action that moves the task forward. When the screenshot shows the task
is complete, answer "done". If the task is impossible, answer "none".

You ARE the assistant carrying out the request: never wait for an assistant, app or window to
act for you, and never click the app that is running you. For standard editing use the keyboard
instead of hunting through menus: ctrl+a select all, ctrl+c copy, ctrl+v paste, ctrl+z undo,
ctrl+s save, ctrl+f find. Use "wait" only for a page that is
still loading. If a step you already took did not change the screen, do something different
instead of repeating it: a keyboard action ("hotkey") is often more reliable than a click, and
a "type" action may also carry the "element" of the field to type into (it is clicked first)
and "submit": true to press Enter afterwards, so a search is ONE action, not three.
Set "final": true when this one action completes the whole request (opening a tab, pressing a
shortcut, clicking the one button asked for, submitting a search): the task then ends without
another look, so the same thing is never done twice.

Clickable elements are marked on the screenshot with red numbered boxes and listed as
"[number] Kind 'Name'". For a click, answer with that number in "element". Only if the thing
to click has no box, describe it in "target" precisely enough to find it visually.

You MUST respond strictly with valid JSON conforming to this schema:
{
  "action": "click" | "double_click" | "right_click" | "type" | "hotkey" | "scroll" | "wait" | "done" | "none",
  "element": integer (number of the marked element to click, or to scroll over),
  "direction": "up" | "down" (for scroll: moves about half a page),
  "target": string (visual description, only when no marked element fits),
  "text": string (text to type, if action is type),
  "submit": true/false (press Enter after typing, e.g. to run a search),
  "final": true/false (this action alone completes the request),
  "keys": list of strings (keys to press, e.g. ["ctrl", "c"]),
  "explanation": string (brief explanation of what you are clicking/doing)
}
"""


def _to_data_url(img: Image.Image) -> str:
    """JPEG is ~3x smaller than PNG; upload size dominated call latency."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


JEV_CLICK_CONFIDENCE = 0.9  # below this the vision model double-checks Jev's pick


def _window_box(hwnd: int, size) -> tuple:
    """Screen rect of the target window clipped to the screenshot, or the full screen."""
    try:
        import win32gui
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        box = (max(0, left), max(0, top), min(size[0], right), min(size[1], bottom))
        if box[2] - box[0] > 50 and box[3] - box[1] > 50:
            return box
    except Exception:
        pass
    return (0, 0, size[0], size[1])


def _inside(rect, box) -> bool:
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    return box[0] <= cx < box[2] and box[1] <= cy < box[3]


def _draw_marks(img: Image.Image, elements, box) -> Image.Image:
    """Set-of-marks: numbered red boxes so the model answers with a number, not pixels."""
    from PIL import ImageDraw
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    for i, e in enumerate(elements, 1):
        l, t, r, b = (e.rect[0] - box[0], e.rect[1] - box[1], e.rect[2] - box[0], e.rect[3] - box[1])
        draw.rectangle((l, t, r, b), outline=(255, 0, 0), width=2)
        draw.rectangle((l, t, l + 8 + 7 * len(str(i)), t + 14), fill=(255, 0, 0))
        draw.text((l + 3, t + 1), str(i), fill=(255, 255, 255))
    return img


def _parse_json(text: str) -> dict:
    """Models wrap JSON in prose or fences, or echo the schema first: scan every {...} and
    keep the last one that parses and names an action (a greedy regex spliced two together)."""
    dec, found, i = json.JSONDecoder(), None, text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
            if isinstance(obj, dict) and "action" in obj:
                found = obj
            i = text.find("{", end)
        except ValueError:
            i = text.find("{", i + 1)
    if found is None:
        raise ValueError(f"no JSON action in model reply: {text[:80]!r}")
    return found


class VisionAgent:
    """Plans one GUI action at a time from a screenshot via an OpenRouter vision model."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "qwen/qwen3-vl-8b-instruct",
        mock_mode: bool = False,
        api_base: str = OPENROUTER_BASE,
    ):
        self.api_base = api_base.rstrip("/")  # OpenAI-compatible: OpenRouter, OpenAI, LM Studio...
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.model_name = model_name
        self.mock_mode = mock_mode or not self.api_key
        self.guardrail = SafetyGuardrail()

    def _ask(self, image_url: str, text: str, system: str = "") -> dict:
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": text},
        ]})
        body = {"model": self.model_name, "messages": messages, "temperature": 0}
        if "openrouter.ai" in self.api_base:  # other endpoints reject the unknown field
            # If the provider is busy, OpenRouter tries these instead of failing the task
            body["models"] = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
            body["provider"] = {"sort": "latency"}  # measured: qwen 0.7s steady vs 0.9-2.0s
        last = None
        for attempt in range(3):
            r = _session.post(self.api_base + "/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"},
                              json=body, timeout=60)
            if r.status_code == 200:
                return _parse_json(r.json()["choices"][0]["message"]["content"])
            last = f"{r.status_code} {r.text[:120]}"
            if r.status_code not in (429, 500, 502, 503, 529):  # not worth retrying
                break
            wait = float(r.headers.get("retry-after") or 2 * (attempt + 1))
            print(f"[VISION]: {r.status_code} from the model, retrying in {wait:.0f}s")
            time.sleep(min(wait, 8))
        raise RuntimeError(f"vision model unavailable after retries: {last}")

    def plan_action(
        self, user_command: str, screenshot: Image.Image, history: Optional[List[str]] = None,
        hwnd: int = 0,
    ) -> VisionAction:
        """Ask the model for the next single action toward the user's request."""
        if self.mock_mode:
            return VisionAction(
                action="click",
                x=screenshot.width // 2,
                y=screenshot.height // 2,
                explanation="Mock center click",
            )

        # Work on the target window only: sharper image, fewer distractions, and the
        # OS tells us its elements by name so clicks land on exact rects.
        box = _window_box(hwnd, screenshot.size)
        crop = screenshot.crop(box)
        elements = [e for e in uia.list_elements(hwnd) if _inside(e.rect, box)]
        listing = "\n".join(f"[{i}] {e.kind} '{e.name}'" for i, e in enumerate(elements, 1))

        image = _to_data_url(_draw_marks(crop, elements, box))
        steps = "\n".join(f"{i}. {h}" for i, h in enumerate(history or [], 1)) or "(none yet)"
        prompt = (f"User Request: {user_command}\nSteps already taken:\n{steps}\n"
                  f"Marked elements:\n{listing or '(none)'}")

        # Race: the vision model starts now; if Jev meanwhile finds one obvious click, that
        # wins and the model's answer is simply dropped (saves Jev's ~0.7s when it says none).
        planned = _pool.submit(self._plan, image, prompt, elements, crop.size, box)
        # Fast path: one obvious click on a named element needs no vision result at all.
        if not history and elements:
            picked = jev.choose(
                {"command": user_command, "elements_in_reading_order": listing},
                "Which single element should be clicked to fully carry out this command? "
                "Answer none if it needs typing, several steps, or no element fits.",
                {**{str(i): f"{e.kind} '{e.name}'" for i, e in enumerate(elements, 1)},
                 "none": "No single click completes the command"},
            )
            if picked and picked[0] != "none" and picked[1] >= JEV_CLICK_CONFIDENCE:
                e = elements[int(picked[0]) - 1]
                return VisionAction("click", *e.center, final=True, explanation=f"Click {e.kind} '{e.name}'")

        return planned.result()

    def _plan(self, image: str, prompt: str, elements, crop_size, box) -> VisionAction:
        try:
            data = self._ask(image, prompt, SYSTEM_PROMPT)
            if data.get("action") in ("click", "double_click", "right_click") and not (
                    data.get("element") or data.get("target")):
                # A click with nothing to click wastes a whole step; ask once more, plainly.
                nudge = ('\n\nYour last answer was a click with no element and no target. '
                         'Answer again with "element": <number>.')
                data = self._ask(image, prompt + nudge, SYSTEM_PROMPT)
            x = y = None
            n = data.get("element")
            act = data.get("action")
            if act in ("click", "double_click", "right_click", "type", "scroll") and isinstance(n, int) and 1 <= n <= len(elements):
                x, y = elements[n - 1].center
            elif data.get("action") == "type":
                # No target given: type into the window's own text area rather than
                # blindly at whatever happens to hold focus.
                field = next((e for e in elements if e.kind in ("Document", "Edit")), None)
                if field:
                    x, y = field.center
            elif act in ("click", "double_click", "right_click") and data.get("target"):
                x, y = self._locate(data["target"], image, crop_size)
                x, y = x + box[0], y + box[1]  # crop -> screen coordinates
            return VisionAction(
                action=data.get("action", "none"),
                x=x,
                y=y,
                text=data.get("text"),
                submit=bool(data.get("submit")),
                final=bool(data.get("final")),
                direction="up" if str(data.get("direction", "")).lower() == "up" else "down",
                keys=data.get("keys") or [],
                explanation=data.get("explanation", ""),
            )
        except Exception as e:
            return VisionAction(action="none", explanation=f"Vision API error: {e}")

    def _locate(self, target: str, image_url: str, size) -> tuple:
        """Second call: pure grounding. Asking the planner for coordinates directly was
        inaccurate; a dedicated "find this element" call measured 3/3 on the taskbar."""
        d = self._ask(image_url, 'Return only JSON {"x": int, "y": int}: the center of '
                                 f"{target}, with coordinates normalized to 0-1000 over the image.")
        return round(d["x"] * size[0] / 1000), round(d["y"] * size[1] / 1000)

    def execute_action(self, action: VisionAction) -> bool:
        """Execute the planned visual action via PyAutoGUI."""
        try:
            has_xy = action.x is not None and action.y is not None
            if action.action == "click" and has_xy:
                pyautogui.click(action.x, action.y)
                return True
            elif action.action == "double_click" and has_xy:
                pyautogui.doubleClick(action.x, action.y)
                return True
            elif action.action == "right_click" and has_xy:
                pyautogui.rightClick(action.x, action.y)
                return True
            elif action.action == "scroll":
                if has_xy:
                    pyautogui.moveTo(action.x, action.y)  # the wheel scrolls what is under the mouse
                pyautogui.scroll(-600 if action.direction == "down" else 600)
                return True
            elif action.action == "type" and action.text:
                if action.x is not None and action.y is not None:
                    pyautogui.click(action.x, action.y)  # focus the field first
                type_text(action.text)
                if action.submit:
                    send_hotkey("enter")
                return True
            elif action.action == "hotkey" and action.keys:
                send_hotkey(*action.keys)
                return True
            elif action.action == "wait":
                return True
            return False
        except Exception:
            return False
