"""Command router classifying speech transcriptions into system intents or vision tasks."""

from dataclasses import dataclass
import re
from typing import Dict, List, Optional
from urllib.parse import quote_plus
from src import apps, jev
from src.config import Intent, IntentAction

# Maximum words allowed around a contained trigger for a containment match.
MAX_EXTRA_WORDS = 2
# Below this, a Jev intent guess is not trusted and the command goes to vision.
JEV_MIN_CONFIDENCE = 0.8


@dataclass
class RouteResult:
    is_vision: bool
    command: str
    intent: Optional[Intent] = None


class CommandRouter:
    """Routes voice transcriptions to deterministic intents or vision agent."""

    def __init__(self, intents: List[Intent], use_jev: bool = False):
        self.intents = intents
        self.use_jev = use_jev
        self._trigger_map: Dict[str, Intent] = {}
        self._build_index()
        self._intents_by_name = {i.name: i for i in intents}
        # Jev picks one of these; "none" sends the command on to the vision agent
        self._jev_options = {i.name: "; ".join(i.triggers[:4]) for i in intents}
        self._jev_options["none"] = "Anything else: clicking, typing, choosing items on screen, multi-step tasks"

    def _normalize(self, text: str) -> str:
        """Strip punctuation, collapse spaces, and convert to lower case."""
        # Replace non-alphanumeric (except single spaces) with empty string
        cleaned = re.sub(r"[^\w\s]", "", text)
        # Drop articles so "open the browser" matches the "open browser" trigger
        return " ".join(w for w in cleaned.lower().split() if w not in ("the", "a", "an"))

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

        # 2. Key phrase containment match (ordered by longest trigger first).
        # Only counts for short utterances: after removing the matched
        # trigger, at most MAX_EXTRA_WORDS words may remain.
        sorted_triggers = sorted(self._trigger_map.keys(), key=len, reverse=True)
        for trigger in sorted_triggers:
            if " " not in trigger:
                continue  # one word ("print", "cut") only counts alone: "print my name" is not ctrl+p
            # Check whole phrase match or word boundary
            pattern = r"\b" + re.escape(trigger) + r"\b"
            if re.search(pattern, clean_text):
                remainder = re.sub(pattern, " ", clean_text, count=1)
                if len(remainder.split()) <= MAX_EXTRA_WORDS:
                    return RouteResult(
                        is_vision=False,
                        command=utterance.strip(),
                        intent=self._trigger_map[trigger],
                    )

        # 3. Commands that carry their own argument: open <app>, type <text>, go to <site>
        slot = self._slot_intent(utterance.strip(), clean_text)
        if slot:
            return RouteResult(is_vision=False, command=utterance.strip(), intent=slot)

        # 4. Jev understands paraphrases the trigger list misses ("maximise it", "make it louder")
        if self.use_jev:
            picked = jev.choose(
                {"spoken_command": utterance.strip()},
                "Which desktop action does this spoken command ask for? The text comes from "
                "speech recognition, so words may be misheard (\"new debt\" for \"new tab\"). "
                "Answer none unless one action fully does what was asked.",
                self._jev_options,
            )
            if picked and picked[0] in self._intents_by_name and picked[1] >= JEV_MIN_CONFIDENCE:
                return RouteResult(
                    is_vision=False,
                    command=utterance.strip(),
                    intent=self._intents_by_name[picked[0]],
                )

        # 5. Fallback to Tier 2 Vision Agent
        return RouteResult(
            is_vision=True,
            command=utterance.strip(),
            intent=None,
        )

    def _slot_intent(self, raw: str, clean: str) -> Optional[Intent]:
        """Deterministic argument commands; None lets Jev and vision handle the rest."""
        m = re.match(r"(?:type|dictate)\s+(.+)", raw, re.I)
        if m:
            return _make("type_text", IntentAction("type_text", target=_dictation(m.group(1).strip())))
        # A dotted word is a site ("youtube.com"), unless it is a file ("notepad.exe")
        m = re.match(r"(?:go to|open|visit)\s+((?:https?://)?[\w-]+(?:\.[\w-]+)*\.([a-z]{2,12})(?:/\S*)?)$",
                     raw.rstrip(". "), re.I)
        if m and m.group(2).lower() not in FILE_EXTENSIONS:
            url = m.group(1) if "://" in m.group(1) else "https://" + m.group(1)
            return _make("open_url", IntentAction("open_url", target=url))
        m = re.match(r"(?:google|search google for|search web for|look up)\s+(.+)", clean)
        if m:
            url = "https://www.google.com/search?q=" + quote_plus(m.group(1))
            return _make("web_search", IntentAction("open_url", target=url))
        m = re.match(r"search (\w+) for (.+)", clean)
        if m and m.group(1) in SITE_SEARCH:
            url = SITE_SEARCH[m.group(1)] + quote_plus(m.group(2))
            return _make("site_search", IntentAction("open_url", target=url))
        m = re.match(r"(?:press|hit)\s+(.+)$", clean)
        if m:
            keys = _parse_keys(m.group(1))
            if keys:
                return _make("press_keys", IntentAction("hotkey", keys=keys))
        m = re.match(r"(?:switch to|go to|focus|show me|bring up)\s+(.+)$", clean)
        if m:
            win = apps.find_window(m.group(1))
            if win:
                return _make("focus_window", IntentAction("focus_window", target=str(win[0]), command=win[1]))
            if m.group(1) in SITES:  # "go to youtube": no such window open, so open the site
                return _make("open_url", IntentAction("open_url", target=SITES[m.group(1)]))
        m = re.match(r"(?:minimize|minimise|minimized)\s+(.+)$", clean)
        if m:
            win = apps.find_window(m.group(1))
            if win:
                return _make("minimize_window", IntentAction("minimize_window", target=str(win[0]), command=win[1]))
        m = re.match(r"(?:maximize|maximise|maximized)\s+(.+)$", clean)
        if m:
            win = apps.find_window(m.group(1))
            if win:
                return _make("maximize_window", IntentAction("maximize_window", target=str(win[0]), command=win[1]))
        m = re.match(r"(?:restore|unmaximize|unmaximise)\s+(.+)$", clean)
        if m:
            win = apps.find_window(m.group(1))
            if win:
                return _make("restore_window", IntentAction("restore_window", target=str(win[0]), command=win[1]))
        m = re.match(r"(?:close|quit|exit)\s+(.+)$", clean)
        if m and m.group(1) not in ("tab", "this tab", "window", "this", "it"):
            target = m.group(1)
            win = apps.find_window(target)
            if win:
                intent = _make("close_window", IntentAction("close_window", target=str(win[0]), command=win[1]))
                intent.is_destructive = True  # same as "close window": ask before closing
                return intent
            # Only say "<target> is not open" if target is a known installed app;
            # UI targets like "close popup", "close sidebar", "exit fullscreen" fall through to Vision.
            try:
                known_app = apps.find(target, allow_jev=False)
            except TypeError:
                known_app = apps.find(target)
            if known_app:
                return _make("not_open", IntentAction("say", target=f"{target} is not open"))
            return None
        m = re.match(r"(?:open|launch|start|run)\s+(.+?)(?:\s+app)?$", clean)
        if m:
            found = apps.find(m.group(1))
            if found:
                return _make("open_app", IntentAction("open_app", target=found[1], command=found[0]))
        return None


def _make(name: str, action: IntentAction) -> Intent:
    return Intent(name=name, category="slot", triggers=[], action=action)


KEY_ALIASES = {"control": "ctrl", "windows": "win", "window": "win", "escape": "esc",
               "return": "enter", "plus": "+", "minus": "-", "equals": "=", "period": ".",
               "comma": ",", "slash": "/", "spacebar": "space", "arrow": "", "key": "", "and": "",
               "then": "", "delete": "delete", "del": "delete"}
MERGE = {("page", "down"): "pagedown", ("page", "up"): "pageup", ("print", "screen"): "printscreen",
         ("caps", "lock"): "capslock"}


def _parse_keys(spoken: str) -> Optional[List[str]]:
    """ "control shift t" -> ["ctrl", "shift", "t"]; None if any word is not a key."""
    import pyautogui
    words = [KEY_ALIASES.get(w, w) for w in spoken.replace("+", " ").split()]
    words = [w for w in words if w]
    keys, i = [], 0
    while i < len(words):
        pair = tuple(words[i:i + 2])
        if pair in MERGE:
            keys.append(MERGE[pair])
            i += 2
            continue
        keys.append(words[i])
        i += 1
    return keys if keys and all(k in pyautogui.KEYBOARD_KEYS for k in keys) else None


FILE_EXTENSIONS = {"exe", "txt", "docx", "doc", "pdf", "py", "png", "jpg", "jpeg", "xlsx", "csv",
                   "pptx", "zip", "mp3", "mp4", "lnk", "bat", "md", "json"}
SITES = {"youtube": "https://www.youtube.com", "gmail": "https://mail.google.com",
         "google": "https://www.google.com", "github": "https://github.com",
         "reddit": "https://www.reddit.com", "amazon": "https://www.amazon.com",
         "netflix": "https://www.netflix.com", "facebook": "https://www.facebook.com",
         "linkedin": "https://www.linkedin.com", "twitter": "https://x.com", "x": "https://x.com",
         "wikipedia": "https://en.wikipedia.org", "chatgpt": "https://chatgpt.com",
         "maps": "https://maps.google.com", "google maps": "https://maps.google.com"}
SITE_SEARCH = {"youtube": "https://www.youtube.com/results?search_query=",
               "amazon": "https://www.amazon.com/s?k=", "github": "https://github.com/search?q=",
               "reddit": "https://www.reddit.com/search/?q=", "wikipedia": "https://en.wikipedia.org/w/index.php?search=",
               "maps": "https://www.google.com/maps/search/", "google": "https://www.google.com/search?q="}
# Spoken dictation words -> what they mean when typed
DICTATION = [(r"\s*\bnew paragraph\b\s*", "\n\n"), (r"\s*\bnew line\b\s*", "\n"),
             (r"\s*\bcomma\b", ","), (r"\s*\bfull stop\b", "."), (r"\s*\bperiod\b", "."),
             (r"\s*\bquestion mark\b", "?"), (r"\s*\bexclamation (?:mark|point)\b", "!")]


def _dictation(text: str) -> str:
    """ "hello comma world new line bye" -> "hello, world\nbye" """
    for pattern, repl in DICTATION:
        text = re.sub(pattern, repl, text, flags=re.I)
    return text
