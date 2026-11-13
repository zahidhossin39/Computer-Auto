"""TypeSafe Jev via OpenRouter's Decisions endpoint: fast typed choices (~0.7s, ~$0.00003/call)."""

import os
from typing import Optional

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
_session = requests.Session()  # keep-alive: skips a TLS handshake per call


def choose(state: dict, instructions: str, options: dict) -> Optional[tuple]:
    """Ask Jev to pick one key of `options` ({key: description}, max 255).

    Returns (choice, confidence), or None if Jev is unavailable, so callers
    always keep their non-Jev fallback path.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key or not options:
        return None
    try:
        r = _session.post(
            DECISIONS_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": MODEL,
                "state": state,
                "questions": {"q": {"type": "choice", "instructions": instructions, "criteria": options}},
            },
            timeout=15,
        )
        r.raise_for_status()
        answer = r.json()["answers"]["q"]
        return answer["choice"], float(answer["confidence"])
    except Exception as e:
        print(f"[JEV]: unavailable ({e})")
        return None
