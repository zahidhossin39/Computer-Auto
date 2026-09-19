"""Tier 2 Vision Agent: a vision model on OpenRouter plans GUI actions from screenshots."""

import base64
from dataclasses import dataclass, field
import io
import json
import os
import re
from typing import List, Optional
from PIL import Image
import pyautogui
import requests

from src.executor.guardrail import SafetyGuardrail

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class VisionAction:
    action: str  # "click", "type", "hotkey", "wait", "done", "none"
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    keys: List[str] = field(default_factory=list)
    explanation: str = ""


SYSTEM_PROMPT = """You are a desktop GUI automation agent working step by step.
You get the user request, the steps already taken, and a fresh screenshot of the screen.
Decide the ONE next action that moves the task forward. When the screenshot shows the task
is complete, answer "done". If the task is impossible, answer "none".

For a click, describe the element to click in "target" precisely enough to find it
visually (label, icon look, and where it is, e.g. "the Chrome icon in the taskbar").

You MUST respond strictly with valid JSON conforming to this schema:
{
  "action": "click" | "type" | "hotkey" | "wait" | "done" | "none",
  "target": string (visual description of the element, for click),
  "text": string (text to type, if action is type),
  "keys": list of strings (keys to press, e.g. ["ctrl", "c"]),
  "explanation": string (brief explanation of what you are clicking/doing)
}
"""


def _to_data_url(img: Image.Image) -> str:
    """JPEG is ~3x smaller than PNG; upload size dominated call latency."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _parse_json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or code fences; take the outermost object."""
    return json.loads(re.search(r"[{].*[}]", text, re.S).group(0))


class VisionAgent:
    """Plans one GUI action at a time from a screenshot via an OpenRouter vision model."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "qwen/qwen3-vl-8b-instruct",
        mock_mode: bool = False,
    ):
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
        r = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model_name, "messages": messages, "temperature": 0},
            timeout=60,
        )
        r.raise_for_status()
        return _parse_json(r.json()["choices"][0]["message"]["content"])

    def plan_action(
        self, user_command: str, screenshot: Image.Image, history: Optional[List[str]] = None
    ) -> VisionAction:
        """Ask the model for the next single action toward the user's request."""
        if self.mock_mode:
            return VisionAction(
                action="click",
                x=screenshot.width // 2,
                y=screenshot.height // 2,
                explanation="Mock center click",
            )

        image = _to_data_url(screenshot)
        steps = "\n".join(f"{i}. {h}" for i, h in enumerate(history or [], 1)) or "(none yet)"
        prompt = f"User Request: {user_command}\nSteps already taken:\n{steps}"

        try:
            data = self._ask(image, prompt, SYSTEM_PROMPT)
            x = y = None
            if data.get("action") == "click" and data.get("target"):
                x, y = self._locate(data["target"], image, screenshot.size)
            return VisionAction(
                action=data.get("action", "none"),
                x=x,
                y=y,
                text=data.get("text"),
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
            if action.action == "click" and action.x is not None and action.y is not None:
                pyautogui.click(action.x, action.y)
                return True
            elif action.action == "type" and action.text:
                pyautogui.write(action.text)
                return True
            elif action.action == "hotkey" and action.keys:
                pyautogui.hotkey(*action.keys)
                return True
            elif action.action == "wait":
                return True
            return False
        except Exception:
            return False
