"""Windows UI Automation: list a window's clickable elements by name and exact screen rect.

Clicking an element the OS names ("Zaid hossain" profile button) beats asking a vision
model to find pixels, which miscounts ordinals like "the fifth profile".
"""

from dataclasses import dataclass
from typing import List, Tuple

try:
    import uiautomation as auto
except ImportError:  # optional: the agent falls back to pixel grounding
    auto = None

CLICKABLE = {
    "ButtonControl", "HyperlinkControl", "ListItemControl", "MenuItemControl", "TabItemControl",
    "EditControl", "CheckBoxControl", "RadioButtonControl", "ComboBoxControl", "TreeItemControl",
    "SplitButtonControl",
}
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
    out: List[Element] = []
    try:
        with auto.UIAutomationInitializerInThread():  # safe from worker threads
            root = auto.ControlFromHandle(hwnd)
            # ponytail: full tree walk costs ~2s on a busy Chrome page; switch to a UIA
            # CacheRequest/FindAll if per-step latency matters more than simplicity.
            for ctl, _ in auto.WalkControl(root, maxDepth=40):
                if ctl.ControlTypeName not in CLICKABLE or not ctl.Name or ctl.IsOffscreen:
                    continue
                r = ctl.BoundingRectangle
                if r.width() <= 0 or r.height() <= 0:
                    continue
                out.append(Element(ctl.Name.strip()[:80], ctl.ControlTypeName[:-7],
                                   (r.left, r.top, r.right, r.bottom)))
                if len(out) >= MAX_ELEMENTS:
                    break
    except Exception as e:
        print(f"[UIA]: could not read window elements ({e})")
    # Row-major order (rows bucketed by 20px) so "fifth" means what a person would count
    out.sort(key=lambda e: (e.rect[1] // 20, e.rect[0]))
    return out
