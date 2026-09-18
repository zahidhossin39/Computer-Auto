"""Tests for Safety Guardrail System."""

import pytest
from src.executor.guardrail import SafetyGuardrail


def test_destructive_keywords_trigger_confirmation():
    """Verify that dangerous phrases require confirmation."""
    guard = SafetyGuardrail()

    dangerous_phrases = [
        "delete this file",
        "remove all items in folder",
        "drop the database table",
        "format the drive",
        "erase my hard drive",
        "send email to everyone",
        "confirm purchase for 50 dollars",
        "checkout and pay now",
    ]

    for phrase in dangerous_phrases:
        assert guard.requires_confirmation(phrase) is True, f"Failed for: {phrase}"


def test_benign_commands_do_not_require_confirmation():
    """Verify that harmless commands proceed without interruption."""
    guard = SafetyGuardrail()

    benign_phrases = [
        "turn up the volume",
        "open notepad",
        "maximize this window",
        "snap left",
        "play music",
        "search for weather forecast",
    ]

    for phrase in benign_phrases:
        assert guard.requires_confirmation(phrase) is False, f"Failed for: {phrase}"


def test_intent_marked_destructive_triggers_confirmation():
    """Verify that an intent with is_destructive=True triggers confirmation even if phrase is simple."""
    guard = SafetyGuardrail()
    assert (
        guard.requires_confirmation("close window", is_intent_destructive=True)
        is True
    )


def test_confirmation_prompt_formatting():
    """Verify natural confirmation prompt generation."""
    guard = SafetyGuardrail()
    prompt = guard.format_confirmation_prompt("delete document.txt")
    assert "delete document.txt" in prompt
    assert "proceed" in prompt.lower() or "sure" in prompt.lower()
