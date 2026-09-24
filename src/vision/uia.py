"""Windows UI Automation: list a window's clickable elements by name and exact screen rect.

Clicking an element the OS names ("Zaid hossain" profile button) beats asking a vision
model to find pixels, which miscounts ordinals like "the fifth profile".
"""

import time
from dataclasses import dataclass
from typing import List, Tuple

try:
    import uiautomation as auto
    from uiautomation.uiautomation import _AutomationClient as _client
except ImportError:  # optional: the agent falls back to pixel grounding
    auto = None

CLICKABLE = {
    "ButtonControl", "HyperlinkControl", "ListItemControl", "MenuItemControl", "TabItemControl",
    "EditControl", "CheckBoxControl", "RadioButtonControl", "ComboBoxControl", "TreeItemControl",
    "SplitButtonControl",
    "DocumentControl",  # the editable body of Notepad, Word, a browser page
}
TREE_SCOPE_DESCENDANTS = 4
MAX_ELEMENTS = 200  # Jev choices cap at 255; also keeps the planner prompt small


@dataclass
class Element:
    name: str
    kind: str  # "Button", "Edit", ...
    rect: Tuple[int, int, int, int]  # left, top, right, bottom in screen pixels

    @property
    def center(self) -> Tuple[int, int]:
        return (self.rect[0] + self.rect[2]) // 2, (self.rect[1] + self.rect[3]) // 2


def list_elements(hwnd: int) -> List[Element]:
    """Named, visible, clickable elements of one window, in reading order (top-left first)."""
    if auto is None or not hwnd:
        return []
    for attempt in (1, 2):  # a busy app (Chrome mid-load) can throw a transient COM error
        out = _walk(hwnd)
        if out:
            break
        time.sleep(0.3)
    # Row-major order (rows bucketed by 20px) so "fifth" means what a person would count
    out.sort(key=lambda e: (e.rect[1] // 20, e.rect[0]))
    return out


def _walk(hwnd: int) -> List[Element]:
    """One bulk COM call (FindAll + CacheRequest) instead of a walk that asks for every
    property of every node: same elements, ~0.1s instead of ~0.8-2s on Chrome."""
    out: List[Element] = []
    try:
        with auto.UIAutomationInitializerInThread():  # safe from worker threads
            ia = _client.instance().IUIAutomation
            req = ia.CreateCacheRequest()
            for pid in (auto.PropertyId.NameProperty, auto.PropertyId.ControlTypeProperty,
                        auto.PropertyId.BoundingRectangleProperty, auto.PropertyId.IsOffscreenProperty):
                req.AddProperty(pid)
            req.TreeFilter = ia.RawViewCondition  # the control view hides Chrome's tab strip buttons
            cond = ia.CreateOrConditionFromArray([
                ia.CreatePropertyCondition(auto.PropertyId.ControlTypeProperty, getattr(auto.ControlType, n))
                for n in CLICKABLE])
            found = ia.ElementFromHandle(hwnd).FindAllBuildCache(TREE_SCOPE_DESCENDANTS, cond, req)
            for i in range(found.Length):
                el = found.GetElement(i)
                name, r = el.CachedName, el.CachedBoundingRectangle
                if el.CachedIsOffscreen or not name or r.right <= r.left or r.bottom <= r.top:
                    continue
                out.append(Element(name.strip()[:80], auto.ControlTypeNames[el.CachedControlType][:-7],
                                   (r.left, r.top, r.right, r.bottom)))
                if len(out) >= MAX_ELEMENTS:
                    break
    except Exception as e:
        print(f"[UIA]: could not read window elements ({e})")
    return out
