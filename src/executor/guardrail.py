"""Safety guardrail system preventing accidental execution of destructive actions."""

import re
from typing import List


class SafetyGuardrail:
    """Verifies actions and requires verbal confirmation for high-stakes/destructive operations."""

    DESTRUCTIVE_PATTERNS: List[str] = [
        r"\bdelete\b",
        r"\bremove\b",
        r"\bdrop\b",
        r"\berase\b",
        r"\bformat\b",
        r"\bpurge\b",
        r"\bkill\b",
        r"\bterminate\b",
        r"\bpay\b",
        r"\bpurchase\b",
        r"\bbuy\b",
        r"\bcheckout\b",
        r"\bsend\s+email\b",
        r"\bsend\s+message\b",
        r"\buninstall\b",
        r"\btrash\b",
        r"\brecycle\s+bin\b",
        r"\bsubscribe\b",
        r"\btransfer\b",
        r"\bwire\b",
        r"\bsell\b",
        r"\bplace\s+order\b",
    ]

    def __init__(self, additional_patterns: List[str] = None):
        self.patterns = list(self.DESTRUCTIVE_PATTERNS)
        if additional_patterns:
            self.patterns.extend(additional_patterns)
        self._compiled_regex = [
            re.compile(p, re.IGNORECASE) for p in self.patterns
        ]

    def requires_confirmation(
        self, command: str, is_intent_destructive: bool = False
    ) -> bool:
        """Check if command matches destructive patterns or has explicit destructive flag."""
        if is_intent_destructive:
            return True

        clean = command.strip()
        for regex in self._compiled_regex:
            if regex.search(clean):
                return True

        return False

    def format_confirmation_prompt(self, command: str) -> str:
        """Generate voice confirmation prompt for the assistant to speak."""
        return (
            f"You requested to {command.strip()}. "
            "Are you sure you want to proceed?"
        )
