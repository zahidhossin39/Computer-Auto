"""Tier 2 Vision Agent powered by Google Gemini Flash for GUI navigation."""

from dataclasses import dataclass, field
import io
import json
import os
from typing import List, Optional
from PIL import Image
import pyautogui

from src.executor.guardrail import SafetyGuardrail

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


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


def _to_jpeg(img: Image.Image):
    """JPEG is ~3x smaller than the default PNG upload, which dominated call latency."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=85)
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


class GeminiVisionAgent:
    """Uses Google Gemini Flash to visually inspect screenshots and execute actions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-3.5-flash-lite",
        mock_mode: bool = False,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model_name
        self.mock_mode = mock_mode
        self.guardrail = SafetyGuardrail()
        self._client = None

        if not self.mock_mode and self.api_key and genai is not None:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                self._client = None

    def plan_action(
        self, user_command: str, screenshot: Image.Image, history: Optional[List[str]] = None
    ) -> VisionAction:
        """Analyze screenshot with Gemini Flash and return structured action."""
        if self.mock_mode or self._client is None:
            return VisionAction(
                action="click",
                x=screenshot.width // 2,
                y=screenshot.height // 2,
                explanation="Mock center click",
            )

        image = _to_jpeg(screenshot)
        steps = "\n".join(f"{i}. {h}" for i, h in enumerate(history or [], 1)) or "(none yet)"
        prompt = f"User Request: {user_command}\nSteps already taken:\n{steps}"

        try:
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.1,
            )
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=[image, prompt],
                config=config,
            )
            data = json.loads(response.text)
            x = y = None
            if data.get("action") == "click" and data.get("target"):
                x, y = self._locate(data["target"], image, screenshot.size)
            return VisionAction(
                action=data.get("action", "none"),
                x=x,
                y=y,
                text=data.get("text"),
                keys=data.get("keys", []),
                explanation=data.get("explanation", ""),
            )
        except Exception as e:
            return VisionAction(
                action="none",
                explanation=f"Error calling Gemini Vision API: {e}",
            )

    def _locate(self, target: str, image, size) -> tuple:
        """Second call: pure grounding. Gemini is trained on box_2d detection, which is far
        more accurate than asking the planner for coordinates directly."""
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=[image, f'Return JSON {{"box_2d": [ymin, xmin, ymax, xmax]}} '
                                  f"normalized 0-1000 for: {target}"],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", temperature=0,
            ),
        )
        data = json.loads(response.text)
        data = data[0] if isinstance(data, list) else data
        y0, x0, y1, x1 = data["box_2d"]
        return (round((x0 + x1) / 2 * size[0] / 1000),
                round((y0 + y1) / 2 * size[1] / 1000))

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
