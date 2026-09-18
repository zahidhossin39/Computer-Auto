"""Tier 2 Vision Agent powered by Google Gemini Flash for GUI navigation."""

from dataclasses import dataclass, field
import json
import os
from typing import List, Optional
from PIL import Image
import pyautogui

from src.executor.guardrail import SafetyGuardrail

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


@dataclass
class VisionAction:
    action: str  # "click", "type", "hotkey", "wait", "none"
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    keys: List[str] = field(default_factory=list)
    explanation: str = ""


SYSTEM_PROMPT = """You are a desktop GUI automation agent.
You are given a user request and a screenshot of the computer screen.
Analyze the visual layout, find the element relevant to the user request, and determine the exact (X, Y) pixel coordinates to interact with.

You MUST respond strictly with valid JSON conforming to this schema:
{
  "action": "click" | "type" | "hotkey" | "wait" | "none",
  "x": integer (pixel x coordinate),
  "y": integer (pixel y coordinate),
  "text": string (text to type, if action is type),
  "keys": list of strings (keys to press, e.g. ["ctrl", "c"]),
  "explanation": string (brief explanation of what you are clicking/doing)
}
"""


class GeminiVisionAgent:
    """Uses Google Gemini Flash to visually inspect screenshots and execute actions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
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
        self, user_command: str, screenshot: Image.Image
    ) -> VisionAction:
        """Analyze screenshot with Gemini Flash and return structured action."""
        if self.mock_mode or self._client is None:
            return VisionAction(
                action="click",
                x=screenshot.width // 2,
                y=screenshot.height // 2,
                explanation="Mock center click",
            )

        prompt = f"User Request: {user_command}\nScreen size: {screenshot.width}x{screenshot.height}"

        try:
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.1,
            )
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=[screenshot, prompt],
                config=config,
            )
            data = json.loads(response.text)
            return VisionAction(
                action=data.get("action", "none"),
                x=data.get("x"),
                y=data.get("y"),
                text=data.get("text"),
                keys=data.get("keys", []),
                explanation=data.get("explanation", ""),
            )
        except Exception as e:
            return VisionAction(
                action="none",
                explanation=f"Error calling Gemini Vision API: {e}",
            )

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
