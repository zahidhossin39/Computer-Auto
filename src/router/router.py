"""Command router classifying speech transcriptions into system intents or vision tasks."""

from dataclasses import dataclass
import re
from typing import Dict, List, Optional
from src.config import Intent


@dataclass
class RouteResult:
    is_vision: bool
    command: str
    intent: Optional[Intent] = None


class CommandRouter:
    """Routes voice transcriptions to deterministic intents or vision agent."""

    def __init__(self, intents: List[Intent]):
        self.intents = intents
        self._trigger_map: Dict[str, Intent] = {}
        self._build_index()

    def _normalize(self, text: str) -> str:
        """Strip punctuation, collapse spaces, and convert to lower case."""
        # Replace non-alphanumeric (except single spaces) with empty string
        cleaned = re.sub(r"[^\w\s]", "", text)
        return " ".join(cleaned.lower().split())

    def _build_index(self) -> None:
        """Index triggers for sub-millisecond lookup."""
        for intent in self.intents:
            for trigger in intent.triggers:
                norm_trigger = self._normalize(trigger)
                if norm_trigger:
                    self._trigger_map[norm_trigger] = intent

    def route(self, utterance: str) -> RouteResult:
        """Classify utterance into an Intent or Vision task."""
        clean_text = self._normalize(utterance)

        if not clean_text:
            return RouteResult(is_vision=False, command="", intent=None)

        # 1. Exact match
        if clean_text in self._trigger_map:
            return RouteResult(
                is_vision=False,
                command=utterance.strip(),
                intent=self._trigger_map[clean_text],
            )

        # 2. Key phrase containment match (ordered by longest trigger first)
        sorted_triggers = sorted(self._trigger_map.keys(), key=len, reverse=True)
        for trigger in sorted_triggers:
            # Check whole phrase match or word boundary
            pattern = r"\b" + re.escape(trigger) + r"\b"
            if re.search(pattern, clean_text):
                return RouteResult(
                    is_vision=False,
                    command=utterance.strip(),
                    intent=self._trigger_map[trigger],
                )

        # 3. Fallback to Tier 2 Vision Agent
        return RouteResult(
            is_vision=True,
            command=utterance.strip(),
            intent=None,
        )
