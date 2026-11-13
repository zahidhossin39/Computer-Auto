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

POLITE_PREFIX_RE = re.compile(
    r"^(?:(?:please|okay|ok|hey|computer|nova|can you|could you|would you|will you|"
    r"i want to|i want you to|id like to|go ahead and|just)\s+)+",
    re.I,
)
# Words in trigger containment remainder that indicate a specific argument/slot rather than filler
SLOT_REMAINDER_WORDS = {
    "profile", "profiles", "gmail", "gmails", "email", "emails", "inbox", "account", "accounts",
    "number", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
    "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "already", "opened", "work", "business", "search", "type", "write", "dictate",
}


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
        """Strip punctuation, collapse spaces, convert to lower case, and apply phonetic fixes."""
        cleaned = re.sub(r"[^\w\s]", "", text).lower()
        cleaned = re.sub(r"\b(?:new debt|new dep)\b", "new tab", cleaned)
        cleaned = re.sub(r"\b(?:not pet|not bad|note bad|not pad)\b", "notepad", cleaned)
        cleaned = re.sub(r"\b(?:minima's|minimas|minimise|minimised)\b", "minimize", cleaned)
        cleaned = re.sub(r"\b(?:cloud code|cloud)\b", "claude", cleaned)
        cleaned = re.sub(r"\b(?:upset)\b", "website", cleaned)
        cleaned = re.sub(r"\b(?:g mail|gee mail|ji mail|jemail)\b", "gmail", cleaned)
        cleaned = re.sub(r"\b(?:pro file|profyle)\b", "profile", cleaned)
        cleaned = re.sub(r"\b(?:numba|nmbr)\b", "number", cleaned)
        # Drop articles so "open the browser" matches the "open browser" trigger
        return " ".join(w for w in cleaned.split() if w not in ("the", "a", "an"))

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

        polite_clean = POLITE_PREFIX_RE.sub("", clean_text).strip() or clean_text

        # 1. Exact match (raw normalized or after stripping leading polite filler like "please")
        if clean_text in self._trigger_map:
            return RouteResult(
                is_vision=False,
                command=utterance.strip(),
                intent=self._trigger_map[clean_text],
            )
        if polite_clean in self._trigger_map:
            return RouteResult(
                is_vision=False,
                command=utterance.strip(),
                intent=self._trigger_map[polite_clean],
            )

        # 2. Deterministic argument / slot commands: open <profile/gmail>, open <app>, type <text>,
        #    go to <site>, minimize/maximize/focus <window>. Runs before fuzzy containment so
        #    "open chrome 3rd profile" or "open chrome already open" is not hijacked by "open chrome".
        slot = self._slot_intent(utterance.strip(), clean_text)
        if not slot and polite_clean != clean_text:
            slot = self._slot_intent(utterance.strip(), polite_clean)
        if slot:
            return RouteResult(is_vision=False, command=utterance.strip(), intent=slot)

        # 3. Key phrase containment match (ordered by longest trigger first).
        # Only counts for short utterances: after removing the matched
        # trigger, at most MAX_EXTRA_WORDS words may remain and none may be slot arguments.
        sorted_triggers = sorted(self._trigger_map.keys(), key=len, reverse=True)
        for trigger in sorted_triggers:
            if " " not in trigger:
                continue  # one word ("print", "cut") only counts alone: "print my name" is not ctrl+p
            pattern = r"\b" + re.escape(trigger) + r"\b"
            if re.search(pattern, clean_text):
                remainder_words = re.sub(pattern, " ", clean_text, count=1).split()
                if len(remainder_words) <= MAX_EXTRA_WORDS and not (set(remainder_words) & SLOT_REMAINDER_WORDS):
                    return RouteResult(
                        is_vision=False,
                        command=utterance.strip(),
                        intent=self._trigger_map[trigger],
                    )

        # 4. Jev decision model: understands paraphrases and natural intent ("make it louder",
        #    "open my 5th gmail account", "bring back discord") and turns them into fast commands.
        if self.use_jev:
            jev_intent = self._jev_route(utterance.strip(), clean_text)
            if jev_intent is not None:
                return RouteResult(
                    is_vision=False,
                    command=utterance.strip(),
                    intent=jev_intent,
                )

        # 5. Fallback to Tier 2 Vision Agent
        return RouteResult(
            is_vision=True,
            command=utterance.strip(),
            intent=None,
        )

    def _jev_route(self, raw: str, clean: str = "") -> Optional[Intent]:
        """Use TypeSafe Jev decision model to map natural speech onto deterministic commands."""
        options = dict(self._jev_options)
        try:
            for p in apps.chrome_profiles()[:12]:
                idx = p["index"]
                pdir = p["dir"]
                label = f"#{idx} {p['name']} ({p['email'] or pdir})"
                options[f"chrome_gmail:{pdir}"] = f"Open Gmail / email #{idx} ({label}) in Chrome"
                options[f"chrome_profile:{pdir}"] = f"Open / switch to Chrome profile #{idx} ({label})"
        except Exception:
            pass

        try:
            for hwnd, title, exe in apps.open_windows()[:12]:
                short_title = title[:40].replace(":", " ")
                options[f"focus_win:{hwnd}:{short_title}"] = f"Switch to / focus / open existing window '{short_title}' ({exe})"
                options[f"min_win:{hwnd}:{short_title}"] = f"Minimize window '{short_title}' ({exe})"
                options[f"max_win:{hwnd}:{short_title}"] = f"Maximize window '{short_title}' ({exe})"
                options[f"close_win:{hwnd}:{short_title}"] = f"Close window '{short_title}' ({exe})"
        except Exception:
            pass

        for site_key, site_url in SITES.items():
            if len(options) < 245:
                options[f"open_site:{site_key}"] = f"Open {site_key} website ({site_url})"

        for app_key, (disp, _app_id) in apps.COMMON_APPS.items():
            if len(options) < 252:
                options[f"open_app:{app_key}"] = f"Open / launch {disp} application"

        picked = jev.choose(
            {"spoken_command": raw},
            "Which desktop action does this spoken command ask for? The text comes from "
            "speech recognition, so words may be misheard (\"new debt\" for \"new tab\", "
            "\"third number gmail\" for Gmail #3). "
            "Answer none unless one action fully does what was asked.",
            options,
        )
        if not picked or picked[1] < JEV_MIN_CONFIDENCE:
            return None

        choice = picked[0]
        if choice in self._intents_by_name:
            return self._intents_by_name[choice]
        if choice.startswith("chrome_gmail:"):
            pdir = choice.split(":", 1)[1]
            return _make(
                "open_chrome_gmail",
                IntentAction("launch_app", target="chrome.exe", command=pdir, args=[f"--profile-directory={pdir}", "https://mail.google.com"]),
            )
        if choice.startswith("chrome_profile:"):
            pdir = choice.split(":", 1)[1]
            return _make(
                "open_chrome_profile",
                IntentAction("launch_app", target="chrome.exe", command=pdir, args=[f"--profile-directory={pdir}"]),
            )
        if choice.startswith("focus_win:"):
            parts = choice.split(":", 2)
            return _make("focus_window", IntentAction("focus_window", target=parts[1], command=parts[2] if len(parts) > 2 else ""))
        if choice.startswith("min_win:"):
            parts = choice.split(":", 2)
            return _make("minimize_window", IntentAction("minimize_window", target=parts[1], command=parts[2] if len(parts) > 2 else ""))
        if choice.startswith("max_win:"):
            parts = choice.split(":", 2)
            return _make("maximize_window", IntentAction("maximize_window", target=parts[1], command=parts[2] if len(parts) > 2 else ""))
        if choice.startswith("close_win:"):
            parts = choice.split(":", 2)
            intent = _make("close_window", IntentAction("close_window", target=parts[1], command=parts[2] if len(parts) > 2 else ""))
            intent.is_destructive = False
            return intent
        if choice.startswith(("open_site:", "site:")):
            site_key = choice.split(":", 1)[1]
            if site_key in SITES:
                return _make("open_url", IntentAction("open_url", target=SITES[site_key]))
        if choice.startswith("open_app:"):
            app_key = choice.split(":", 1)[1]
            try:
                found = apps.find(app_key, allow_jev=False)
            except TypeError:
                found = apps.find(app_key)
            if found:
                return _make("open_app", IntentAction("open_app", target=found[1], command=found[0]))
        return None

    def _match_chrome_profile_slot(self, clean: str) -> Optional[Intent]:
        """Match commands targeting a specific Chrome profile or numbered/named Gmail account."""
        m = re.match(
            r"(?:in\s+(?:chrome|browser)\s+)?(?:open|launch|start|run|switch to|switch back to|go to|focus|show|bring up|choose|select|pick|click|use)\s+(.+)$",
            clean,
        )
        if not m:
            return None
        rest = m.group(1).strip()
        words = rest.split()
        if len(words) > 8 or (words and words[-1] in ("and", "or", "from")):
            return None

        gmail_words = {"gmail", "gmails", "email", "emails", "inbox"}
        profile_words = {"profile", "profiles", "account", "accounts"}
        has_gmail = bool(set(words) & gmail_words)
        has_profile = bool(set(words) & profile_words)
        if not (has_gmail or has_profile):
            return None

        qualifiers = [
            w for w in words
            if w not in (gmail_words | profile_words | {"chrome", "google", "browser", "my", "this", "that", "in", "on", "of", "number", "no", "num"})
        ]
        if not qualifiers:
            return None

        prof = apps.find_chrome_profile(rest)
        if not prof:
            return None

        pdir = prof["dir"]
        if has_gmail:
            label = f"{prof['name']} ({prof['email'] or pdir})"
            return _make(
                "open_chrome_gmail",
                IntentAction(
                    "launch_app",
                    target="chrome.exe",
                    command=label,
                    args=[f"--profile-directory={pdir}", "https://mail.google.com"],
                ),
            )
        label = f"{prof['name']} ({pdir})"
        return _make(
            "open_chrome_profile",
            IntentAction(
                "launch_app",
                target="chrome.exe",
                command=label,
                args=[f"--profile-directory={pdir}"],
            ),
        )

    def _slot_intent(self, raw: str, clean: str) -> Optional[Intent]:
        """Deterministic argument commands; None lets Jev and vision handle the rest."""
        m = re.match(r"(?:in\s+(?:the\s+)?(?:search\s+bar|search|address\s+bar|url\s+bar)\s*,?\s*(?:type|enter|search for|write)\s+(.+))", clean)
        if m:
            return _make("search_in_browser", IntentAction("search_in_browser", target=_dictation(m.group(1).strip())))
        m = re.match(r"(?:type|enter|write)\s+(.+?)\s+in\s+(?:the\s+)?(?:search\s+bar|search|address\s+bar|url\s+bar)$", clean)
        if m:
            return _make("search_in_browser", IntentAction("search_in_browser", target=_dictation(m.group(1).strip())))

        # Chrome profile or numbered/named Gmail account ("open 3rd gmail", "open third number profile")
        chrome_prof_intent = self._match_chrome_profile_slot(clean)
        if chrome_prof_intent is not None:
            return chrome_prof_intent

        # Typed into specific target window: "in notepad type hello world", "type in the notepad i'm working on it"
        m = re.match(r"(?:in\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\s*,?\s*(?:type|write|dictate)\s+(.+))", clean)
        if m:
            win_target, text_payload = m.group(1).strip(), m.group(2).strip()
            win = apps.find_window(win_target)
            if win:
                return _make("type_in_window", IntentAction("type_in_window", command=win[1], target=_dictation(text_payload), args=[str(win[0])]))
            try:
                known = apps.find(win_target, allow_jev=False)
            except TypeError:
                known = apps.find(win_target)
            if known:
                return _make("not_open", IntentAction("say", target=f"{win_target} is not open"))

        m = re.match(r"(?:type|write|dictate)\s+(?:in|into)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+(?:the\s+(?:thing|text)(?:\s+youre\s+gonna\s+type\s+is)?|that|this|the\s+following))?\s*[:,\s]\s*(.+)", clean)
        if m:
            win_target, text_payload = m.group(1).strip(), m.group(2).strip()
            win = apps.find_window(win_target)
            if win:
                return _make("type_in_window", IntentAction("type_in_window", command=win[1], target=_dictation(text_payload), args=[str(win[0])]))
            try:
                known = apps.find(win_target, allow_jev=False)
            except TypeError:
                known = apps.find(win_target)
            if known:
                return _make("not_open", IntentAction("say", target=f"{win_target} is not open"))

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
        # Switch to / focus / bring up / open existing window
        m = re.match(r"(?:switch to|switch back to|go to|go back to|focus|show me|show|bring up|bring back|open(?: the)?)\s+(.+?)(?:\s+(?:that is|which is)?\s*(?:already\s+)?open(?:ed)?(?:\s+on(?:\s+the)?(?:\s+screen)?)?)?$", clean)
        if m:
            target = m.group(1).strip()
            win = apps.find_window(target)
            if win:
                return _make("focus_window", IntentAction("focus_window", target=str(win[0]), command=win[1]))
            if target in SITES:  # "go to youtube": no such window open, so open the site
                return _make("open_url", IntentAction("open_url", target=SITES[target]))
        m = re.match(r"(?:minimize|minimise|minimized|minimas|minima's)\s+(.+)$", clean)
        if m:
            target = m.group(1).strip()
            win = apps.find_window(target)
            if win:
                return _make("minimize_window", IntentAction("minimize_window", target=str(win[0]), command=win[1]))
            clean_target = " ".join(w for w in target.split() if w not in ("this", "my", "that", "the", "a", "an", "window", "app"))
            if not clean_target:
                return _make("minimize_window", IntentAction("system_action", command="window_minimize_active"))
            try:
                known = apps.find(clean_target, allow_jev=False)
            except TypeError:
                known = apps.find(clean_target)
            if known:
                return _make("not_open", IntentAction("say", target=f"{clean_target} is not open"))

        m = re.match(r"(?:maximize|maximise|maximized)\s+(.+)$", clean)
        if m:
            target = m.group(1).strip()
            win = apps.find_window(target)
            if win:
                return _make("maximize_window", IntentAction("maximize_window", target=str(win[0]), command=win[1]))
            clean_target = " ".join(w for w in target.split() if w not in ("this", "my", "that", "the", "a", "an", "window", "app"))
            if not clean_target:
                return _make("maximize_window", IntentAction("system_action", command="window_maximize_active"))
            try:
                known = apps.find(clean_target, allow_jev=False)
            except TypeError:
                known = apps.find(clean_target)
            if known:
                return _make("not_open", IntentAction("say", target=f"{clean_target} is not open"))

        m = re.match(r"(?:restore|unmaximize|unmaximise)\s+(.+)$", clean)
        if m:
            target = m.group(1).strip()
            win = apps.find_window(target)
            if win:
                return _make("restore_window", IntentAction("restore_window", target=str(win[0]), command=win[1]))
            clean_target = " ".join(w for w in target.split() if w not in ("this", "my", "that", "the", "a", "an", "window", "app"))
            if not clean_target:
                return _make("restore_window", IntentAction("system_action", command="window_restore_active"))
            try:
                known = apps.find(clean_target, allow_jev=False)
            except TypeError:
                known = apps.find(clean_target)
            if known:
                return _make("not_open", IntentAction("say", target=f"{clean_target} is not open"))
        m = re.match(r"(?:close|quit|exit)\s+(.+)$", clean)
        if m and m.group(1) not in ("tab", "this tab", "window", "this", "it"):
            target = m.group(1)
            win = apps.find_window(target)
            if win:
                intent = _make("close_window", IntentAction("close_window", target=str(win[0]), command=win[1]))
                intent.is_destructive = False
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
            try:
                found = apps.find(m.group(1), allow_jev=not self.use_jev)
            except TypeError:
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
