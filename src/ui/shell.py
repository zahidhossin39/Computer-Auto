"""Material Design 3 pill-first Command Studio shell for Computer-Auto.

Preserves two core invariants:
  - It never hides itself during a vision run (ghost mode shrinks, fades, and
    becomes click-through so the screen stays unobstructed without losing the app).
  - All public attributes/methods used by main.py and regression tests remain stable.
"""

import os
import queue
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# Attach to the interactive desktop before tkinter loads (IDE terminals otherwise
# render our windows into an invisible desktop).
if sys.platform == "win32":
    try:
        import ctypes

        _hdesk = ctypes.windll.user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if _hdesk:
            ctypes.windll.user32.SetThreadDesktop(_hdesk)
    except Exception:
        pass

import tkinter as tk
from tkinter import ttk

try:
    import sounddevice as sd
except ImportError:
    sd = None

from src.config import load_settings, save_settings
from src.ui.theme import (
    ACCENT,
    CHROMA,
    DONE,
    FONT,
    MIC,
    PANEL_H,
    PANEL_W,
    PILL_H,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    STATE_WORD,
    WORK,
    Theme,
    get_theme,
    state_color,
)
from src.ui.tray import TrayIcon

VISION_MODELS = [
    "qwen/qwen3-vl-8b-instruct",
    "google/gemini-3.1-flash-lite",
    "qwen/qwen3-vl-30b-a3b-instruct",
    "qwen/qwen3-vl-32b-instruct",
]

VOICE_ENGINES = {
    "On-device Parakeet (free, offline, ~0.5s)": "",
    "Cloud gpt-4o-transcribe (best with names, ~1.3s)": "openai/gpt-4o-transcribe",
    "Cloud gpt-4o-mini-transcribe (cheaper)": "openai/gpt-4o-mini-transcribe",
}

QUICK_EXAMPLES = [
    "Open Notepad & type hello",
    "Snap left",
    "Search YouTube for lofi",
    "Take screenshot",
]

MAX_LOG_LINES = 400


def _virtual_screen(w: int, h: int) -> tuple:
    """(left, top, width, height) spanning every monitor; primary screen elsewhere."""
    try:
        import ctypes

        m = ctypes.windll.user32.GetSystemMetrics
        vx, vy, vw, vh = m(76), m(77), m(78), m(79)
        if vw > 0 and vh > 0:
            return vx, vy, vw, vh
    except Exception:
        pass
    return 0, 0, w, h


def _round_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, r: int, **kw):
    """Draw a smooth rounded rectangle on a Tk Canvas."""
    pts = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class AppShell:
    """Material Design 3 pill-first control surface for the daemon."""

    def __init__(
        self,
        daemon: Optional[Any] = None,
        on_toggle_listening: Optional[Callable[[], None]] = None,
        on_panic: Optional[Callable[[], None]] = None,
        on_run_command: Optional[Callable[[str], None]] = None,
        on_switch_to_hud: Optional[Callable[[], None]] = None,  # kept for main.py compatibility
        on_guardrail_reply: Optional[Callable[[bool], None]] = None,
    ):
        self.daemon = daemon
        self.on_toggle_listening = on_toggle_listening
        self.on_panic = on_panic
        self.on_run_command = on_run_command
        self.on_guardrail_reply = on_guardrail_reply

        settings = load_settings()
        self.theme: Theme = get_theme(settings.get("theme", "dark"))
        self._tray_enabled: bool = bool(settings.get("minimize_to_tray", False))
        self._minimized_to_tray: bool = False
        self._tray: Optional[TrayIcon] = None

        self.root: Optional[tk.Tk] = None
        self._is_running = False
        self.expanded = False
        self.ghost = False
        self.current_state = "ready"
        self.current_message = "Ready"
        self.current_detail = "Double-tap Ctrl to talk"
        self._log_lines: List[str] = []
        self._drag = (0, 0)
        self._moved = False
        self._active_tab = "Studio"
        self._audio_level = 0.0
        self._pulse_phase = 0
        self._pulse_job: Optional[str] = None
        self._theme_updaters: List[Callable[[Theme], None]] = []
        self._scroll_canvases: List[tk.Canvas] = []
        self._panel_size = (PANEL_W, PANEL_H)
        self._model_downloading = False
        self._fallback_dl_cancel: Optional[threading.Event] = None
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

    # ---------- construction ----------

    def init_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("Computer-Auto")
        self.root.overrideredirect(True)
        self.root.configure(bg=CHROMA)
        self.root.attributes("-topmost", True)
        try:
            self.root.wm_attributes("-transparentcolor", CHROMA)
        except Exception:
            self.root.configure(bg=self.theme.surface_container_lowest)

        self.canvas = tk.Canvas(self.root, bg=CHROMA, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        for widget in (self.root, self.canvas):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        self._build_pill()
        self._build_panel()
        self._style_ttk()
        self._apply_theme_to_widgets()
        self._apply_state()
        self._layout_pill()

        if self._tray_enabled:
            self._ensure_tray()

        self.root.bind("<Escape>", lambda e: self._panic())
        self._is_running = True
        self.log("Shell ready.")

    def _register_theme(self, fn: Callable[[Theme], None]) -> None:
        self._theme_updaters.append(fn)

    def _style_ttk(self) -> None:
        t = self.theme
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background=t.surface_container, foreground=t.on_surface)
        style.configure(
            "M3.TCombobox",
            fieldbackground=t.surface_container_highest,
            background=t.surface_container_high,
            foreground=t.on_surface,
            arrowcolor=t.on_surface_variant,
            bordercolor=t.outline_variant,
            lightcolor=t.surface_container_highest,
            darkcolor=t.surface_container_highest,
        )
        style.map(
            "M3.TCombobox",
            fieldbackground=[("readonly", t.surface_container_highest)],
            foreground=[("readonly", t.on_surface)],
        )
        style.configure(
            "M3.Vertical.TScrollbar",
            background=t.surface_container_highest,
            troughcolor=t.surface_container_low,
            bordercolor=t.surface_container_low,
            arrowcolor=t.on_surface_variant,
        )
        if self.root:
            self.root.option_add("*TCombobox*Listbox.background", t.surface_container_high)
            self.root.option_add("*TCombobox*Listbox.foreground", t.on_surface)
            self.root.option_add("*TCombobox*Listbox.selectBackground", t.primary_container)
            self.root.option_add("*TCombobox*Listbox.selectForeground", t.on_primary_container)

    def set_theme(self, mode: str) -> None:
        """Switch between Material Design 3 'dark' and 'light' themes live."""
        self.theme = get_theme(mode)
        if hasattr(self, "theme_var"):
            self.theme_var.set(self.theme.name)
        if self.root is None:
            return
        self._style_ttk()
        self._apply_theme_to_widgets()
        self._apply_state()
        if self.expanded:
            self._redraw_panel_bg()
        else:
            self._layout_pill()

    def _toggle_theme(self) -> None:
        new_mode = "light" if self.theme.is_dark else "dark"
        self.set_theme(new_mode)
        # Persist theme choice immediately without clobbering other settings
        s = load_settings()
        s["theme"] = new_mode
        save_settings(s)

    def _apply_theme_to_widgets(self) -> None:
        t = self.theme
        for fn in self._theme_updaters:
            try:
                fn(t)
            except Exception:
                pass
        self._show_tab(self._active_tab)

    # ---------- pill ----------

    def _build_pill(self) -> None:
        t = self.theme
        self.pill = tk.Frame(self.canvas, bg=t.surface_container)

        self.dot = tk.Canvas(self.pill, width=20, height=20, bg=t.surface_container, highlightthickness=0)
        self._ring_id = self.dot.create_oval(2, 2, 18, 18, outline="", width=2)
        self._dot_id = self.dot.create_oval(5, 5, 15, 15, fill=t.idle_dot, outline="")
        self.dot.pack(side="left", padx=(2, SPACE_SM))

        self.state_lbl = tk.Label(self.pill, text="Ready", bg=t.surface_container, fg=t.on_surface, font=t.label_large)
        self.state_lbl.pack(side="left")

        self.detail_lbl = tk.Label(self.pill, text="", bg=t.surface_container, fg=t.on_surface_variant, font=t.body_medium)
        self.detail_lbl.pack(side="left", padx=(SPACE_SM, 0))

        self.step_lbl = tk.Label(self.pill, text="", bg=t.surface_container, fg=t.primary, font=t.label_small)
        self.step_lbl.pack(side="left", padx=(SPACE_SM, 0))

        # Inline guardrail action controls (shown only in "guardrail" state)
        self.pill_guardrail_frame = tk.Frame(self.pill, bg=t.surface_container)
        self.pill_confirm_btn = tk.Button(
            self.pill_guardrail_frame,
            text="Confirm",
            command=lambda: self._resolve_guardrail(True),
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            font=t.label_small,
        )
        self.pill_confirm_btn.pack(side="left", padx=(SPACE_SM, SPACE_XS))
        self.pill_cancel_btn = tk.Button(
            self.pill_guardrail_frame,
            text="Cancel",
            command=lambda: self._resolve_guardrail(False),
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            font=t.label_small,
        )
        self.pill_cancel_btn.pack(side="left")

        # Compact direct Mic toggle & Expand buttons right on the pill
        self.pill_actions = tk.Frame(self.pill, bg=t.surface_container)
        self.pill_actions.pack(side="left", padx=(SPACE_MD, 0))

        self.pill_mic_btn = tk.Button(
            self.pill_actions,
            text="Mic",
            command=self._toggle,
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            font=t.label_small,
        )
        self.pill_mic_btn.pack(side="left", padx=(0, SPACE_XS))

        self.pill_expand_btn = tk.Button(
            self.pill_actions,
            text="Studio",
            command=self._expand,
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            font=t.label_small,
        )
        self.pill_expand_btn.pack(side="left")

        for w in (self.pill, self.state_lbl, self.detail_lbl, self.dot, self.step_lbl):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._click_pill)
        self._pill_window = None

        def _retheme_pill(th: Theme) -> None:
            for w in (self.pill, self.dot, self.state_lbl, self.detail_lbl, self.step_lbl, self.pill_guardrail_frame, self.pill_actions):
                w.configure(bg=th.surface_container)
            self.state_lbl.configure(fg=th.on_surface)
            self.detail_lbl.configure(fg=th.on_surface_variant)
            self.step_lbl.configure(fg=th.primary)
            self.pill_confirm_btn.configure(
                bg=th.success_container,
                fg=th.on_success_container,
                activebackground=th.success,
                activeforeground=th.on_success,
            )
            self.pill_cancel_btn.configure(
                bg=th.error_container,
                fg=th.on_error_container,
                activebackground=th.error,
                activeforeground=th.on_error,
            )
            self.pill_expand_btn.configure(
                bg=th.surface_container_highest,
                fg=th.on_surface,
                activebackground=th.primary_container,
                activeforeground=th.on_primary_container,
            )

        self._register_theme(_retheme_pill)

    def _layout_pill(self) -> None:
        """Size the window to the pill's own width; the pill grows with its text."""
        self.expanded = False
        self.canvas.delete("bg")
        self.panel.place_forget()
        self.pill.update_idletasks()
        w = max(240, self.pill.winfo_reqwidth() + 34)
        h = PILL_H
        self._place_window(w, h, bottom_right=not hasattr(self, "_pos"))
        self.canvas.config(width=w, height=h)
        _round_rect(
            self.canvas,
            1,
            1,
            w - 1,
            h - 1,
            h // 2,
            fill=self.theme.surface_container,
            outline=self.theme.outline_variant,
            tags="bg",
        )
        if self._pill_window:
            self.canvas.delete(self._pill_window)
        self._pill_window = self.canvas.create_window(17, h // 2, window=self.pill, anchor="w")

    def _click_pill(self, _event=None) -> None:
        if self._moved or self.ghost:
            return
        self._expand()

    # ---------- panel ----------

    def _build_panel(self) -> None:
        t = self.theme
        self.panel = tk.Frame(self.canvas, bg=t.surface_container)

        # Header bar (participates in dragging)
        head = tk.Frame(self.panel, bg=t.surface_container)
        head.pack(fill="x", padx=SPACE_LG, pady=(14, SPACE_SM))

        title_wrap = tk.Frame(head, bg=t.surface_container)
        title_wrap.pack(side="left")
        app_title = tk.Label(title_wrap, text="Computer-Auto", bg=t.surface_container, fg=t.on_surface, font=t.title_large)
        app_title.pack(side="left")
        self.header_badge = tk.Label(
            title_wrap,
            text="Ready",
            bg=t.surface_container_highest,
            fg=t.on_surface_variant,
            font=t.label_small,
            padx=8,
            pady=2,
        )
        self.header_badge.pack(side="left", padx=(SPACE_SM, 0))
        esc_hint = tk.Label(title_wrap, text="Esc stops", bg=t.surface_container, fg=t.on_surface_variant, font=t.body_small)
        esc_hint.pack(side="left", padx=(SPACE_SM, 0))

        self.quit_chip = self._chip(head, "Quit", self._quit)
        self.quit_chip.pack(side="right")
        self.collapse_chip = self._chip(head, "Collapse", self._collapse)
        self.collapse_chip.pack(side="right", padx=(0, SPACE_XS))
        self.tray_chip = self._chip(head, "Tray", self.minimize_to_tray)
        self.tray_chip.pack(side="right", padx=(0, SPACE_XS))
        self.theme_chip = self._chip(head, "Light" if t.is_dark else "Dark", self._toggle_theme)
        self.theme_chip.pack(side="right", padx=(0, SPACE_XS))

        for w in (head, title_wrap, app_title, self.header_badge, esc_hint):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        # Primary action bar + Audio meter
        bar = tk.Frame(self.panel, bg=t.surface_container)
        bar.pack(fill="x", padx=SPACE_LG, pady=(SPACE_XS, 0))

        self.mic_btn = tk.Button(
            bar,
            text="Start listening",
            command=self._toggle,
            relief="flat",
            bg=t.primary,
            fg=t.on_primary,
            activebackground=t.primary_container,
            activeforeground=t.on_primary_container,
            font=t.label_large,
            cursor="hand2",
            bd=0,
            pady=10,
        )
        self.mic_btn.pack(side="left", fill="x", expand=True)

        self.stop_btn = tk.Button(
            bar,
            text="Stop (Esc)",
            command=self._panic,
            relief="flat",
            bg=t.error_container,
            fg=t.on_error_container,
            activebackground=t.error,
            activeforeground=t.on_error,
            font=t.label_medium,
            cursor="hand2",
            bd=0,
            padx=16,
            pady=10,
        )
        self.stop_btn.pack(side="left", padx=(SPACE_SM, 0))

        # Audio level meter bar
        self.level_canvas = tk.Canvas(
            self.panel,
            height=6,
            bg=t.surface_container_highest,
            highlightthickness=0,
            bd=0,
        )
        self.level_canvas.pack(fill="x", padx=SPACE_LG, pady=(SPACE_SM, 0))
        self._level_rect = self.level_canvas.create_rectangle(0, 0, 0, 6, fill=t.primary, outline="")

        # Inline Guardrail Banner in panel (shown only when state == "guardrail")
        self.panel_guardrail_frame = tk.Frame(
            self.panel,
            bg=t.warning_container,
            highlightthickness=1,
            highlightbackground=t.warning,
        )
        self.panel_guardrail_lbl = tk.Label(
            self.panel_guardrail_frame,
            text="Confirmation required",
            bg=t.warning_container,
            fg=t.on_warning_container,
            font=t.label_medium,
            anchor="w",
        )
        self.panel_guardrail_lbl.pack(side="left", fill="x", expand=True, padx=SPACE_MD, pady=SPACE_SM)
        self.panel_cancel_btn = tk.Button(
            self.panel_guardrail_frame,
            text="Cancel",
            command=lambda: self._resolve_guardrail(False),
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            font=t.label_small,
        )
        self.panel_cancel_btn.pack(side="right", padx=(SPACE_XS, SPACE_SM), pady=SPACE_XS)
        self.panel_confirm_btn = tk.Button(
            self.panel_guardrail_frame,
            text="Confirm",
            command=lambda: self._resolve_guardrail(True),
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            font=t.label_small,
        )
        self.panel_confirm_btn.pack(side="right", pady=SPACE_XS)

        # M3 Segmented Tab Bar
        self.tabrow = tk.Frame(
            self.panel,
            bg=t.surface_container_low,
            highlightthickness=1,
            highlightbackground=t.outline_variant,
            padx=4,
            pady=4,
        )
        self.tabrow.pack(fill="x", padx=SPACE_LG, pady=(SPACE_MD, 0))

        self.body = tk.Frame(self.panel, bg=t.surface_container)
        self.body.pack(fill="both", expand=True, padx=SPACE_MD, pady=(SPACE_SM, SPACE_MD))

        self._tabs: Dict[str, tk.Label] = {}
        self._panes: Dict[str, tk.Frame] = {}
        for name in ("Studio", "Commands", "Settings"):
            btn = tk.Label(
                self.tabrow,
                text=name,
                bg=t.surface_container_low,
                fg=t.on_surface_variant,
                font=t.label_medium,
                cursor="hand2",
                padx=14,
                pady=6,
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)
            btn.bind("<Button-1>", lambda e, n=name: self._show_tab(n))
            pane = tk.Frame(self.body, bg=t.surface_container)
            self._tabs[name] = btn
            self._panes[name] = pane

        self._build_studio(self._panes["Studio"])
        self._build_commands(self._panes["Commands"])
        self._build_settings(self._panes["Settings"])
        self._show_tab("Studio")

        def _retheme_panel(th: Theme) -> None:
            for w in (self.panel, head, title_wrap, bar, self.body):
                w.configure(bg=th.surface_container)
            for p in self._panes.values():
                p.configure(bg=th.surface_container)
            app_title.configure(bg=th.surface_container, fg=th.on_surface)
            esc_hint.configure(bg=th.surface_container, fg=th.on_surface_variant)
            self.stop_btn.configure(
                bg=th.error_container,
                fg=th.on_error_container,
                activebackground=th.error,
                activeforeground=th.on_error,
            )
            self.theme_chip.configure(text="Light" if th.is_dark else "Dark")
            for chip in (self.quit_chip, self.collapse_chip, self.tray_chip, self.theme_chip):
                chip.configure(
                    bg=th.surface_container_high,
                    fg=th.on_surface_variant,
                    activebackground=th.surface_container_highest,
                    activeforeground=th.on_surface,
                )
            self.level_canvas.configure(bg=th.surface_container_highest)
            self.tabrow.configure(bg=th.surface_container_low, highlightbackground=th.outline_variant)
            self.panel_guardrail_frame.configure(bg=th.warning_container, highlightbackground=th.warning)
            self.panel_guardrail_lbl.configure(bg=th.warning_container, fg=th.on_warning_container)
            self.panel_confirm_btn.configure(
                bg=th.success,
                fg=th.on_success,
                activebackground=th.success_container,
                activeforeground=th.on_success_container,
            )
            self.panel_cancel_btn.configure(
                bg=th.error,
                fg=th.on_error,
                activebackground=th.error_container,
                activeforeground=th.on_error_container,
            )

        self._register_theme(_retheme_panel)

    def _show_tab(self, name: str) -> None:
        if name == "Activity":
            name = "Studio"
        if name not in self._tabs:
            return
        self._active_tab = name
        t = self.theme
        for other, btn in self._tabs.items():
            on = other == name
            btn.configure(
                bg=t.primary_container if on else t.surface_container_low,
                fg=t.on_primary_container if on else t.on_surface_variant,
                font=t.label_medium if on else t.body_medium,
            )
            self._panes[other].pack_forget()
        self._panes[name].pack(fill="both", expand=True)
        if name == "Settings" and hasattr(self, "offline_model_status"):
            self._refresh_offline_model_ui()

    def _chip(self, parent, text: str, command: Callable[[], None]) -> tk.Button:
        t = self.theme
        return tk.Button(
            parent,
            text=text,
            command=command,
            relief="flat",
            bg=t.surface_container_high,
            fg=t.on_surface_variant,
            activebackground=t.surface_container_highest,
            activeforeground=t.on_surface,
            font=t.label_small,
            cursor="hand2",
            bd=0,
            padx=10,
            pady=4,
        )

    def _card(self, parent, title: Optional[str] = None) -> tk.Frame:
        """Create an M3 tonal elevated card with consistent border and padding."""
        t = self.theme
        card = tk.Frame(
            parent,
            bg=t.surface_container_high,
            highlightthickness=1,
            highlightbackground=t.outline_variant,
            padx=SPACE_MD,
            pady=SPACE_MD,
        )
        title_lbl = None
        if title:
            title_lbl = tk.Label(
                card,
                text=title,
                bg=t.surface_container_high,
                fg=t.primary,
                font=t.label_small,
                anchor="w",
            )
            title_lbl.pack(fill="x", pady=(0, SPACE_SM))

        def _retheme(th: Theme) -> None:
            card.configure(bg=th.surface_container_high, highlightbackground=th.outline_variant)
            if title_lbl is not None:
                title_lbl.configure(bg=th.surface_container_high, fg=th.primary)

        self._register_theme(_retheme)
        return card

    def _label(self, parent, text: str, bg_role: str = "surface_container", fg_role: str = "on_surface_variant", **kw) -> tk.Label:
        t = self.theme
        lbl = tk.Label(
            parent,
            text=text,
            bg=getattr(t, bg_role),
            fg=kw.pop("fg", getattr(t, fg_role)),
            anchor=kw.pop("anchor", "w"),
            font=kw.pop("font", t.body_medium),
            **kw,
        )

        def _retheme(th: Theme) -> None:
            lbl.configure(bg=getattr(th, bg_role), fg=getattr(th, fg_role))

        self._register_theme(_retheme)
        return lbl

    def _dropdown(self, parent, var: tk.StringVar, values: List[str]) -> tk.OptionMenu:
        t = self.theme
        menu = tk.OptionMenu(parent, var, *values)
        menu.config(
            bg=t.surface_container_highest,
            fg=t.on_surface,
            activebackground=t.primary_container,
            activeforeground=t.on_primary_container,
            relief="flat",
            highlightthickness=1,
            highlightbackground=t.outline_variant,
            font=t.body_medium,
            anchor="w",
            direction="below",
            pady=5,
        )
        menu["menu"].config(
            bg=t.surface_container_high,
            fg=t.on_surface,
            activebackground=t.primary_container,
            activeforeground=t.on_primary_container,
            font=t.body_medium,
            relief="flat",
            bd=0,
        )

        def _retheme(th: Theme) -> None:
            menu.config(
                bg=th.surface_container_highest,
                fg=th.on_surface,
                activebackground=th.primary_container,
                activeforeground=th.on_primary_container,
                highlightbackground=th.outline_variant,
            )
            menu["menu"].config(
                bg=th.surface_container_high,
                fg=th.on_surface,
                activebackground=th.primary_container,
                activeforeground=th.on_primary_container,
            )

        self._register_theme(_retheme)
        return menu

    def _entry(self, parent, show: Optional[str] = None) -> tk.Entry:
        t = self.theme
        e = tk.Entry(
            parent,
            bg=t.surface_container_lowest,
            fg=t.on_surface,
            insertbackground=t.primary,
            relief="flat",
            font=t.body_large,
            show=show or "",
        )
        e.configure(highlightthickness=1, highlightbackground=t.outline_variant, highlightcolor=t.primary)

        def _retheme(th: Theme) -> None:
            e.configure(
                bg=th.surface_container_lowest,
                fg=th.on_surface,
                insertbackground=th.primary,
                highlightbackground=th.outline_variant,
                highlightcolor=th.primary,
            )

        self._register_theme(_retheme)
        return e

    def _scrollable_pane(self, parent) -> tk.Frame:
        """Create a vertically scrollable inner frame with MouseWheel support."""
        t = self.theme
        outer = tk.Frame(parent, bg=t.surface_container)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=t.surface_container, highlightthickness=0, bd=0)
        vbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview, style="M3.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=vbar.set)

        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=t.surface_container)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_config(_e=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_config(e) -> None:
            canvas.itemconfigure(win_id, width=e.width)

        def _on_mousewheel(e) -> None:
            delta = -1 * int(e.delta / 120) if e.delta else 0
            if delta:
                canvas.yview_scroll(delta, "units")

        inner.bind("<Configure>", _on_inner_config)
        canvas.bind("<Configure>", _on_canvas_config)
        canvas.bind("<MouseWheel>", _on_mousewheel)
        inner.bind("<MouseWheel>", _on_mousewheel)
        self._scroll_canvases.append(canvas)

        def _retheme(th: Theme) -> None:
            outer.configure(bg=th.surface_container)
            canvas.configure(bg=th.surface_container)
            inner.configure(bg=th.surface_container)

        self._register_theme(_retheme)
        return inner

    # ---------- tabs ----------

    def _build_studio(self, tab: tk.Frame) -> None:
        t = self.theme
        pad = {"padx": SPACE_XS, "pady": (0, SPACE_SM)}

        # Command Prompt Card
        prompt_card = self._card(tab, "COMMAND STUDIO")
        prompt_card.pack(fill="x", **pad)

        self._label(
            prompt_card,
            "Type or speak any task — e.g. \"open notepad and type hello\"",
            bg_role="surface_container_high",
            fg_role="on_surface_variant",
            font=t.body_small,
        ).pack(fill="x", pady=(0, SPACE_XS))

        row = tk.Frame(prompt_card, bg=t.surface_container_high)
        row.pack(fill="x")
        self.cmd_entry = self._entry(row)
        self.cmd_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.cmd_entry.bind("<Return>", lambda e: self._run_typed())

        run_btn = tk.Button(
            row,
            text="Run",
            command=self._run_typed,
            relief="flat",
            bg=t.primary_container,
            fg=t.on_primary_container,
            activebackground=t.primary,
            activeforeground=t.on_primary,
            font=t.label_medium,
            cursor="hand2",
            bd=0,
            padx=16,
        )
        run_btn.pack(side="left", padx=(SPACE_SM, 0), ipady=6)

        # Quick-try chips
        chips_row = tk.Frame(prompt_card, bg=t.surface_container_high)
        chips_row.pack(fill="x", pady=(SPACE_SM, 0))
        example_btns: List[tk.Button] = []
        for ex in QUICK_EXAMPLES:
            b = tk.Button(
                chips_row,
                text=ex,
                command=lambda text=ex: self._run_example(text),
                relief="flat",
                bg=t.surface_container_highest,
                fg=t.on_surface_variant,
                activebackground=t.secondary_container,
                activeforeground=t.on_secondary_container,
                font=t.label_small,
                cursor="hand2",
                bd=0,
                padx=8,
                pady=3,
            )
            b.pack(side="left", padx=(0, SPACE_XS))
            example_btns.append(b)

        # Live Transcript Card
        tx_card = self._card(tab, "LIVE TRANSCRIPT")
        tx_card.pack(fill="x", **pad)
        self.transcript = tk.Label(
            tx_card,
            text="Waiting for voice or typed command…",
            bg=t.surface_container_high,
            fg=t.on_surface,
            font=t.body_medium,
            anchor="w",
            wraplength=500,
            justify="left",
        )
        self.transcript.pack(fill="x")

        # Activity Log Card
        log_card = self._card(tab)
        log_card.pack(fill="both", expand=True, padx=SPACE_XS, pady=(0, SPACE_XS))

        log_hdr = tk.Frame(log_card, bg=t.surface_container_high)
        log_hdr.pack(fill="x", pady=(0, SPACE_XS))
        log_title = tk.Label(
            log_hdr,
            text="ACTIVITY LOG",
            bg=t.surface_container_high,
            fg=t.primary,
            font=t.label_small,
            anchor="w",
        )
        log_title.pack(side="left")
        clear_btn = tk.Button(
            log_hdr,
            text="Clear",
            command=self._clear_log,
            relief="flat",
            bg=t.surface_container_highest,
            fg=t.on_surface_variant,
            font=t.label_small,
            cursor="hand2",
            bd=0,
            padx=8,
            pady=2,
        )
        clear_btn.pack(side="right")

        self.log_text = tk.Text(
            log_card,
            bg=t.surface_container_lowest,
            fg=t.on_surface_variant,
            relief="flat",
            font=t.mono_small,
            height=9,
            wrap="word",
            padx=10,
            pady=8,
            state="disabled",
            highlightthickness=1,
            highlightbackground=t.outline_variant,
        )
        self.log_text.pack(fill="both", expand=True)

        def _retheme_studio(th: Theme) -> None:
            row.configure(bg=th.surface_container_high)
            chips_row.configure(bg=th.surface_container_high)
            run_btn.configure(
                bg=th.primary_container,
                fg=th.on_primary_container,
                activebackground=th.primary,
                activeforeground=th.on_primary,
            )
            for b in example_btns:
                b.configure(
                    bg=th.surface_container_highest,
                    fg=th.on_surface_variant,
                    activebackground=th.secondary_container,
                    activeforeground=th.on_secondary_container,
                )
            self.transcript.configure(bg=th.surface_container_high, fg=th.on_surface)
            log_hdr.configure(bg=th.surface_container_high)
            log_title.configure(bg=th.surface_container_high, fg=th.primary)
            clear_btn.configure(bg=th.surface_container_highest, fg=th.on_surface_variant)
            self.log_text.configure(
                bg=th.surface_container_lowest,
                fg=th.on_surface_variant,
                highlightbackground=th.outline_variant,
            )

        self._register_theme(_retheme_studio)

    def _build_commands(self, tab: tk.Frame) -> None:
        t = self.theme
        search_row = tk.Frame(tab, bg=t.surface_container)
        search_row.pack(fill="x", padx=SPACE_XS, pady=(0, SPACE_SM))

        self._label(search_row, "Filter:", font=t.label_small).pack(side="left", padx=(0, SPACE_SM))
        self.cmd_filter_var = tk.StringVar()
        self.cmd_filter_entry = self._entry(search_row)
        self.cmd_filter_entry.configure(textvariable=self.cmd_filter_var)
        self.cmd_filter_entry.pack(side="left", fill="x", expand=True, ipady=5)

        self._cmd_scroll = self._scrollable_pane(tab)
        self.cmd_filter_var.trace_add("write", lambda *_: self._render_commands_list())
        self._render_commands_list()

        def _retheme(th: Theme) -> None:
            search_row.configure(bg=th.surface_container)

        self._register_theme(_retheme)

    def _render_commands_list(self) -> None:
        if not hasattr(self, "_cmd_scroll"):
            return
        for child in self._cmd_scroll.winfo_children():
            child.destroy()

        t = self.theme
        q = self.cmd_filter_var.get().strip().lower() if hasattr(self, "cmd_filter_var") else ""

        groups: Dict[str, List[tuple]] = {
            "Natural Phrases": [
                ("open <app>", "Launch any installed Windows app"),
                ("type <text>", "Type text into the focused window"),
                ("go to <site.com>", "Open a website in your browser"),
                ("google <query>", "Search the web or YouTube"),
                ("open notepad and type hello", "Chain multiple actions with 'and'"),
            ]
        }

        intents = getattr(getattr(self.daemon, "config", None), "intents", []) or []
        for intent in intents:
            cat = (getattr(intent, "category", "general") or "general").replace("_", " ").title()
            primary = intent.triggers[0] if intent.triggers else intent.name
            alts = ", ".join(intent.triggers[1:4]) or "instant action"
            groups.setdefault(cat, []).append((primary, alts))

        shown_any = False
        for cat, items in groups.items():
            filtered = [
                (cmd, desc)
                for cmd, desc in items
                if not q or q in cmd.lower() or q in desc.lower() or q in cat.lower()
            ]
            if not filtered:
                continue
            shown_any = True
            card = tk.Frame(
                self._cmd_scroll,
                bg=t.surface_container_high,
                highlightthickness=1,
                highlightbackground=t.outline_variant,
                padx=SPACE_MD,
                pady=SPACE_SM,
            )
            card.pack(fill="x", padx=SPACE_XS, pady=(0, SPACE_SM))
            tk.Label(
                card,
                text=cat.upper(),
                bg=t.surface_container_high,
                fg=t.primary,
                font=t.label_small,
                anchor="w",
            ).pack(fill="x", pady=(0, SPACE_XS))

            for cmd, desc in filtered:
                row = tk.Frame(card, bg=t.surface_container_high)
                row.pack(fill="x", pady=2)
                btn = tk.Button(
                    row,
                    text=cmd,
                    command=lambda c=cmd: self._run_or_prefill(c),
                    relief="flat",
                    bg=t.surface_container_highest,
                    fg=t.on_surface,
                    activebackground=t.primary_container,
                    activeforeground=t.on_primary_container,
                    font=t.label_small,
                    cursor="hand2",
                    bd=0,
                    padx=8,
                    pady=3,
                    anchor="w",
                )
                btn.pack(side="left")
                tk.Label(
                    row,
                    text=desc,
                    bg=t.surface_container_high,
                    fg=t.on_surface_variant,
                    font=t.body_small,
                    anchor="w",
                ).pack(side="left", padx=(SPACE_SM, 0), fill="x", expand=True)

        if not shown_any:
            tk.Label(
                self._cmd_scroll,
                text="No matching commands. Anything else is understood by Jev and Vision.",
                bg=t.surface_container,
                fg=t.on_surface_variant,
                font=t.body_medium,
                pady=SPACE_LG,
            ).pack(fill="x")

    def _run_or_prefill(self, cmd: str) -> None:
        if "<" in cmd:
            self._show_tab("Studio")
            self.cmd_entry.delete(0, "end")
            self.cmd_entry.insert(0, cmd)
            self.cmd_entry.focus_set()
        else:
            self._run_example(cmd)

    def _build_settings(self, tab: tk.Frame) -> None:
        s = load_settings()
        t = self.theme
        scroll = self._scrollable_pane(tab)

        # Card 1: AI & Vision
        ai_card = self._card(scroll, "AI & VISION")
        ai_card.pack(fill="x", padx=SPACE_XS, pady=(0, SPACE_SM))

        self._label(ai_card, "OpenRouter API key", bg_role="surface_container_high", font=t.label_small).pack(fill="x", pady=(0, SPACE_XS))
        row = tk.Frame(ai_card, bg=t.surface_container_high)
        row.pack(fill="x")
        self.key_entry = self._entry(row, show="•")
        self.key_entry.insert(0, s.get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY", ""))
        self.key_entry.pack(side="left", fill="x", expand=True, ipady=5)
        test_btn = self._chip(row, "Test", self._test_key)
        test_btn.pack(side="left", padx=(SPACE_SM, 0), ipady=2)
        self.key_status = self._label(ai_card, "Not tested yet", bg_role="surface_container_high", font=t.body_small)
        self.key_status.pack(fill="x", pady=(SPACE_XS, SPACE_SM))

        self._label(ai_card, "Vision model", bg_role="surface_container_high", font=t.label_small).pack(fill="x", pady=(0, SPACE_XS))
        mrow = tk.Frame(ai_card, bg=t.surface_container_high)
        mrow.pack(fill="x")
        self.model_var = tk.StringVar(value=s.get("vision_model", "qwen/qwen3-vl-8b-instruct"))
        self.model_box = ttk.Combobox(mrow, textvariable=self.model_var, values=VISION_MODELS, font=t.body_medium, style="M3.TCombobox")
        self.model_box.pack(side="left", fill="x", expand=True, ipady=3)
        load_btn = self._chip(mrow, "Load list", self._load_models)
        load_btn.pack(side="left", padx=(SPACE_SM, 0), ipady=2)

        self._label(ai_card, "Vision endpoint (OpenAI-compatible) & key", bg_role="surface_container_high", font=t.label_small).pack(fill="x", pady=(SPACE_SM, SPACE_XS))
        erow = tk.Frame(ai_card, bg=t.surface_container_high)
        erow.pack(fill="x")
        self.base_entry = self._entry(erow)
        self.base_entry.insert(0, s.get("vision_api_base") or "https://openrouter.ai/api/v1")
        self.base_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.vkey_entry = self._entry(erow, show="•")
        self.vkey_entry.insert(0, s.get("vision_api_key", ""))
        self.vkey_entry.pack(side="left", padx=(SPACE_SM, 0), ipady=5)

        self._label(
            ai_card,
            "Local endpoints (Ollama, LM Studio, vLLM) work keyless without an API key.",
            bg_role="surface_container_high",
            fg_role="secondary",
            font=t.body_small,
        ).pack(fill="x", pady=(SPACE_XS, 0))

        # Card 2: Voice & Routing
        voice_card = self._card(scroll, "VOICE & ROUTING")
        voice_card.pack(fill="x", padx=SPACE_XS, pady=(0, SPACE_SM))

        self._label(voice_card, "Voice recognition", bg_role="surface_container_high", font=t.label_small).pack(fill="x", pady=(0, SPACE_XS))
        current = s.get("stt_cloud_model", "")
        self.voice_var = tk.StringVar(
            value=next((k for k, v in VOICE_ENGINES.items() if v == current), list(VOICE_ENGINES)[0])
        )
        self._dropdown(voice_card, self.voice_var, list(VOICE_ENGINES)).pack(fill="x")

        # Offline Model section
        offline_box = tk.Frame(
            voice_card,
            bg=t.surface_container_low,
            highlightthickness=1,
            highlightbackground=t.outline_variant,
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        offline_box.pack(fill="x", pady=(SPACE_SM, 0))

        offline_top = tk.Frame(offline_box, bg=t.surface_container_low)
        offline_top.pack(fill="x")
        self.offline_model_status = tk.Label(
            offline_top,
            text=self._offline_model_status_text(),
            bg=t.surface_container_low,
            fg=t.success if self._has_local_model() else t.on_surface_variant,
            font=t.body_small,
            anchor="w",
        )
        self.offline_model_status.pack(side="left", fill="x", expand=True)
        self.offline_model_btn = tk.Button(
            offline_top,
            text="Download Model",
            command=self._toggle_model_download,
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            font=t.label_small,
        )
        self.offline_model_btn.pack(side="right", padx=(SPACE_SM, 0))
        self.offline_model_progress = tk.Label(
            offline_box,
            text="",
            bg=t.surface_container_low,
            fg=t.on_surface_variant,
            font=t.body_small,
            anchor="w",
        )
        self._refresh_offline_model_ui()

        self.jev_var = tk.BooleanVar(value=s.get("use_jev", True))
        jev_chk = tk.Checkbutton(
            voice_card,
            text="Use Jev to understand natural wording (~0.7s, ~$0.00003)",
            variable=self.jev_var,
            bg=t.surface_container_high,
            fg=t.on_surface,
            selectcolor=t.surface_container_lowest,
            activebackground=t.surface_container_high,
            activeforeground=t.on_surface,
            font=t.body_medium,
            anchor="w",
            bd=0,
            highlightthickness=0,
        )
        jev_chk.pack(fill="x", pady=(SPACE_SM, SPACE_XS))

        self._label(voice_card, "Microphone", bg_role="surface_container_high", font=t.label_small).pack(fill="x", pady=(SPACE_XS, SPACE_XS))
        self.device_var = tk.StringVar(value=s.get("audio_device", "System default"))
        self._dropdown(voice_card, self.device_var, self._input_devices()).pack(fill="x")

        # Card 3: Appearance & Behavior
        app_card = self._card(scroll, "APPEARANCE & BEHAVIOR")
        app_card.pack(fill="x", padx=SPACE_XS, pady=(0, SPACE_SM))

        trow = tk.Frame(app_card, bg=t.surface_container_high)
        trow.pack(fill="x", pady=(0, SPACE_SM))
        self._label(trow, "Material Design 3 Theme", bg_role="surface_container_high", font=t.body_medium).pack(side="left")
        self.theme_var = tk.StringVar(value=self.theme.name)
        theme_menu = self._dropdown(trow, self.theme_var, ["dark", "light"])
        theme_menu.pack(side="right")

        self.tray_var = tk.BooleanVar(value=bool(s.get("minimize_to_tray", False)))
        tray_chk = tk.Checkbutton(
            app_card,
            text="Keep Win32 System Tray icon active",
            variable=self.tray_var,
            bg=t.surface_container_high,
            fg=t.on_surface,
            selectcolor=t.surface_container_lowest,
            activebackground=t.surface_container_high,
            activeforeground=t.on_surface,
            font=t.body_medium,
            anchor="w",
            bd=0,
            highlightthickness=0,
        )
        tray_chk.pack(fill="x", pady=(0, SPACE_SM))

        srow = tk.Frame(app_card, bg=t.surface_container_high)
        srow.pack(fill="x")
        self._label(srow, "Max vision steps per task", bg_role="surface_container_high", font=t.body_medium).pack(side="left")
        self.max_steps_var = tk.StringVar(value=str(s.get("max_vision_steps", 8)))
        steps_entry = self._entry(srow)
        steps_entry.configure(textvariable=self.max_steps_var, width=6, justify="center")
        steps_entry.pack(side="right", ipady=3)

        # Save bar
        save_row = tk.Frame(scroll, bg=t.surface_container)
        save_row.pack(fill="x", padx=SPACE_XS, pady=(SPACE_XS, SPACE_SM))
        save_btn = tk.Button(
            save_row,
            text="Save Settings",
            command=self._save_settings,
            relief="flat",
            bg=t.primary,
            fg=t.on_primary,
            activebackground=t.primary_container,
            activeforeground=t.on_primary_container,
            font=t.label_medium,
            cursor="hand2",
            bd=0,
            padx=20,
            pady=8,
        )
        save_btn.pack(side="left")
        self.save_status = self._label(save_row, "", fg_role="success", font=t.body_small)
        self.save_status.pack(side="left", padx=(SPACE_MD, 0))

        def _retheme_settings(th: Theme) -> None:
            for r in (row, mrow, erow, trow, srow):
                r.configure(bg=th.surface_container_high)
            offline_box.configure(bg=th.surface_container_low, highlightbackground=th.outline_variant)
            offline_top.configure(bg=th.surface_container_low)
            self.offline_model_progress.configure(bg=th.surface_container_low, fg=th.on_surface_variant)
            self._refresh_offline_model_ui()
            save_row.configure(bg=th.surface_container)
            for chk in (jev_chk, tray_chk):
                chk.configure(
                    bg=th.surface_container_high,
                    fg=th.on_surface,
                    selectcolor=th.surface_container_lowest,
                    activebackground=th.surface_container_high,
                    activeforeground=th.on_surface,
                )
            for b in (test_btn, load_btn):
                b.configure(
                    bg=th.surface_container_highest,
                    fg=th.on_surface,
                    activebackground=th.primary_container,
                    activeforeground=th.on_primary_container,
                )
            save_btn.configure(
                bg=th.primary,
                fg=th.on_primary,
                activebackground=th.primary_container,
                activeforeground=th.on_primary_container,
            )

        self._register_theme(_retheme_settings)

    # ---------- expand / collapse / ghost / tray ----------

    def _place_window(self, w: int, h: int, bottom_right: bool = False) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if bottom_right or not hasattr(self, "_pos"):
            x, y = max(12, screen_w - w - 28), max(12, screen_h - h - 70)
        else:
            vx, vy, vw, vh = _virtual_screen(screen_w, screen_h)
            x, y = self._pos
            x = max(vx, min(x, vx + vw - w))
            y = max(vy, min(y, vy + vh - h))
        self._pos = (x, y)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _redraw_panel_bg(self) -> None:
        w, h = self._panel_size
        self.canvas.delete("bg")
        _round_rect(
            self.canvas,
            1,
            1,
            w - 1,
            h - 1,
            18,
            fill=self.theme.surface_container,
            outline=self.theme.outline_variant,
            tags="bg",
        )

    def _expand(self) -> None:
        self.expanded = True
        if self._minimized_to_tray:
            self._restore_from_tray()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        vx, vy, vw, vh = _virtual_screen(screen_w, screen_h)

        w = min(PANEL_W, max(440, vw - 32))
        h = min(PANEL_H, max(460, vh - 40))
        self._panel_size = (w, h)

        cur_x, cur_y = getattr(self, "_pos", (vx + 20, vy + 20))
        min_x, max_x = vx + 12, max(vx + 12, vx + vw - w - 12)
        min_y, max_y = vy + 12, max(vy + 12, vy + vh - h - 12)
        x = max(min_x, min(cur_x, max_x))
        y = max(min_y, min(cur_y, max_y))
        self._pos = (x, y)

        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.canvas.config(width=w, height=h)
        if self._pill_window:
            self.canvas.delete(self._pill_window)
            self._pill_window = None
        self._redraw_panel_bg()
        self.panel.place(x=8, y=8, width=w - 16, height=h - 16)

    def _collapse(self) -> None:
        self._layout_pill()

    def _ensure_tray(self) -> None:
        if self._tray is None:
            self._tray = TrayIcon(
                on_restore=lambda: self.root and self.root.after(0, self._restore_from_tray),
                on_toggle_listening=lambda: self.root and self.root.after(0, self._toggle),
                on_quit=lambda: self.root and self.root.after(0, self._quit),
            )
        if self._tray.is_available and not self._tray.is_running:
            self._tray.start()

    def minimize_to_tray(self) -> None:
        """Minimize the shell to the Win32 system tray (no-op fallback if unavailable)."""
        if self.root is None:
            return
        self._ensure_tray()
        if self._tray and self._tray.is_running:
            self._minimized_to_tray = True
            self.root.withdraw()
        else:
            self._collapse()

    def _restore_from_tray(self) -> None:
        self._minimized_to_tray = False
        if self.root:
            self.root.deiconify()
            self.root.attributes("-topmost", True)

    def set_ghost(self, on: bool) -> None:
        """Vision run: shrink, fade and stop taking clicks. Never hide."""
        if self.root is None:
            return
        self.ghost = on
        self.root.after(0, self._apply_ghost, on)
        time.sleep(0.2)

    def _apply_ghost(self, on: bool) -> None:
        if on and self.expanded:
            self._layout_pill()
        try:
            self.root.attributes("-alpha", 0.5 if on else 1.0)
        except Exception:
            pass
        self._set_click_through(on)

    def _set_click_through(self, on: bool) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes

            GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style | WS_EX_TRANSPARENT) if on else (style & ~WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
        except Exception:
            pass

    # ---------- daemon-facing API ----------

    def update_state(self, state: str, message: str, detail: str = "") -> None:
        self.current_state, self.current_message, self.current_detail = state, message, detail
        if self._tray and self._tray.is_running:
            self._tray.update_tooltip(f"Computer-Auto · {STATE_WORD.get(state, state)}")
        if self.root:
            self.root.after(0, self._apply_state)

    def _apply_state(self) -> None:
        t = self.theme
        color = state_color(t, self.current_state)
        word = STATE_WORD.get(self.current_state, self.current_message[:18])
        self.dot.itemconfig(self._dot_id, fill=color)
        self.state_lbl.config(text=word, fg=t.on_surface)

        detail = self.current_detail or self.current_message
        self.detail_lbl.config(text=detail[:42])

        step = ""
        if self.current_message.lower().startswith("vision step"):
            step = self.current_message.replace("Vision step", "Step").split(":")[0]
        self.step_lbl.config(text=step)

        listening = self.current_state == "listening"
        is_guardrail = self.current_state == "guardrail"

        if hasattr(self, "mic_btn"):
            self.mic_btn.config(
                text="Stop listening" if listening else "Start listening",
                bg=t.mic if listening else t.primary,
                fg=t.on_error if listening else t.on_primary,
                activebackground=t.error_container if listening else t.primary_container,
                activeforeground=t.on_error_container if listening else t.on_primary_container,
            )

        if hasattr(self, "pill_mic_btn"):
            self.pill_mic_btn.config(
                text="Stop" if listening else "Mic",
                bg=t.error_container if listening else t.primary_container,
                fg=t.on_error_container if listening else t.on_primary_container,
                activebackground=t.mic if listening else t.primary,
                activeforeground=t.on_error if listening else t.on_primary,
            )

        if hasattr(self, "header_badge"):
            self.header_badge.config(
                text=word,
                bg=t.primary_container if listening else t.surface_container_highest,
                fg=t.on_primary_container if listening else t.on_surface_variant,
            )

        # Guardrail inline controls in pill & panel
        if is_guardrail:
            if not self.pill_guardrail_frame.winfo_ismapped():
                self.pill_guardrail_frame.pack(side="left", before=self.pill_actions)
            self.panel_guardrail_lbl.config(text=detail[:64] or "Confirm this action?")
            if not self.panel_guardrail_frame.winfo_ismapped():
                self.panel_guardrail_frame.pack(fill="x", padx=SPACE_LG, pady=(SPACE_SM, 0), before=self.tabrow)
        else:
            self.pill_guardrail_frame.pack_forget()
            self.panel_guardrail_frame.pack_forget()

        self._sync_pulse()

        if not self.expanded and not self.ghost:
            self._layout_pill()

    def _sync_pulse(self) -> None:
        active = self.current_state in ("listening", "processing", "executing")
        if active and self._pulse_job is None and self.root is not None:
            self._pulse_tick()
        elif not active:
            if self._pulse_job is not None and self.root is not None:
                try:
                    self.root.after_cancel(self._pulse_job)
                except Exception:
                    pass
                self._pulse_job = None
            self.dot.itemconfig(self._ring_id, outline="")

    def _pulse_tick(self) -> None:
        if not self._is_running or self.root is None:
            self._pulse_job = None
            return
        if self.current_state not in ("listening", "processing", "executing"):
            self._pulse_job = None
            self.dot.itemconfig(self._ring_id, outline="")
            return
        self._pulse_phase = (self._pulse_phase + 1) % 6
        color = state_color(self.theme, self.current_state)
        self.dot.itemconfig(self._ring_id, outline=color if self._pulse_phase < 3 else "")
        self._pulse_job = self.root.after(160, self._pulse_tick)

    def set_audio_level(self, level: float) -> None:
        """Update the Studio audio level meter bar (0.0 .. 1.0, thread-safe)."""
        clamped = max(0.0, min(1.0, float(level)))
        self._audio_level = clamped
        if self.root and hasattr(self, "level_canvas"):
            self.root.after(0, self._apply_audio_level, clamped)

    def _apply_audio_level(self, level: float) -> None:
        if not hasattr(self, "level_canvas"):
            return
        w = max(1, self.level_canvas.winfo_width() or (PANEL_W - 48))
        fill_w = int(w * level)
        color = self.theme.mic if self.current_state == "listening" else self.theme.primary
        self.level_canvas.coords(self._level_rect, 0, 0, fill_w, 6)
        self.level_canvas.itemconfig(self._level_rect, fill=color)

    def log(self, message: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')}  {message}"
        self._log_lines.append(line)
        del self._log_lines[:-MAX_LOG_LINES]
        if self.root and hasattr(self, "log_text"):
            self.root.after(0, self._append_log, line)

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        if int(self.log_text.index("end-1c").split(".")[0]) > MAX_LOG_LINES:
            self.log_text.delete("1.0", "101.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_lines.clear()
        if hasattr(self, "log_text"):
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")

    def set_transcript(self, text: str) -> None:
        if self.root and hasattr(self, "transcript"):
            self.root.after(0, lambda: self.transcript.config(text=f'"{text}"'))

    def mainloop(self) -> None:
        if self.root:
            self.root.mainloop()

    # ---------- actions ----------

    def _toggle(self) -> None:
        if self.on_toggle_listening:
            self.on_toggle_listening()

    def _panic(self) -> None:
        if self.on_panic:
            self.on_panic()

    def _resolve_guardrail(self, approved: bool) -> None:
        if self.on_guardrail_reply:
            self.on_guardrail_reply(approved)
        elif self.daemon and hasattr(self.daemon, "confirm_pending"):
            self.daemon.confirm_pending(approved)

    def _run_typed(self) -> None:
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        self.cmd_entry.delete(0, "end")
        if self.on_run_command:
            self.on_run_command(cmd)

    def _run_example(self, text: str) -> None:
        self.cmd_entry.delete(0, "end")
        self.cmd_entry.insert(0, text)
        self._run_typed()

    def _quit(self) -> None:
        self._is_running = False
        if self._pulse_job is not None and self.root is not None:
            try:
                self.root.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        if self._tray is not None:
            self._tray.stop()
            self._tray = None
        if self.daemon and hasattr(self.daemon, "shutdown"):
            self.daemon.shutdown()
        if self.root:
            self.root.destroy()

    def _input_devices(self) -> List[str]:
        names = ["System default"]
        if sd is not None:
            try:
                for i, d in enumerate(sd.query_devices()):
                    if d.get("max_input_channels", 0) > 0:
                        names.append(f"{i}: {d['name'][:40]}")
            except Exception:
                pass
        return names

    def _has_local_model(self) -> bool:
        rec = getattr(self.daemon, "recognizer", None) if self.daemon is not None else None
        return bool(getattr(rec, "has_local_model", False))

    def _offline_model_status_text(self) -> str:
        if self._has_local_model():
            return "Offline Model: Ready (Parakeet INT8)"
        return "Offline Model: Not downloaded (~400 MB for offline voice)"

    def _refresh_offline_model_ui(self) -> None:
        if not hasattr(self, "offline_model_status") or not hasattr(self, "offline_model_btn"):
            return
        t = self.theme
        ready = self._has_local_model()
        self.offline_model_status.configure(
            text=self._offline_model_status_text(),
            bg=t.surface_container_low,
            fg=t.success if ready else t.on_surface_variant,
        )
        if self._model_downloading:
            self.offline_model_btn.configure(
                text="Cancel",
                bg=t.error_container,
                fg=t.on_error_container,
                activebackground=t.error,
                activeforeground=t.on_error,
            )
        else:
            self.offline_model_btn.configure(
                text="Download Model",
                bg=t.primary_container,
                fg=t.on_primary_container,
                activebackground=t.primary,
                activeforeground=t.on_primary,
            )

    def _post_ui(self, fn: Callable[[], None]) -> None:
        """Schedule a callback on the Tk main thread safely, even if mainloop is not active."""
        if not self._is_running or self.root is None:
            return
        self._ui_queue.put(fn)
        try:
            self.root.after(0, self._drain_ui_queue)
        except (RuntimeError, tk.TclError):
            pass

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                fn = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                if self._is_running:
                    fn()
            except Exception:
                pass

    def _set_model_progress(self, text: str) -> None:
        if not self._is_running or not hasattr(self, "offline_model_progress"):
            return
        if text:
            self.offline_model_progress.configure(text=text)
            if not self.offline_model_progress.winfo_ismapped():
                self.offline_model_progress.pack(fill="x", pady=(SPACE_XS, 0))
        else:
            self.offline_model_progress.configure(text="")
            self.offline_model_progress.pack_forget()

    def _toggle_model_download(self) -> None:
        if self._model_downloading:
            if self.daemon is not None and hasattr(self.daemon, "cancel_model_download"):
                self.daemon.cancel_model_download()
            elif self._fallback_dl_cancel is not None:
                self._fallback_dl_cancel.set()
            self._set_model_progress("Canceling download...")
            return

        self._model_downloading = True
        self._refresh_offline_model_ui()
        self._set_model_progress("Starting download...")
        threading.Thread(target=self._download_model_worker, name="model-dl-ui", daemon=True).start()

    def _download_model_worker(self) -> None:
        ok = False
        err_msg = ""

        def on_progress(done_bytes: int, total_bytes: int, stage: str) -> None:
            if total_bytes > 0 and "extract" not in stage.lower():
                pct = min(100, int(done_bytes * 100 / total_bytes))
                done_mb = done_bytes / (1024 * 1024)
                total_mb = total_bytes / (1024 * 1024)
                msg = f"Downloading... {pct}% ({done_mb:.0f} / {total_mb:.0f} MB)"
            else:
                msg = stage
            self._post_ui(lambda m=msg: self._set_model_progress(m))

        try:
            if self.daemon is not None and hasattr(self.daemon, "download_offline_model"):
                ok = bool(self.daemon.download_offline_model(progress_cb=on_progress))
            else:
                from pathlib import Path
                from src.config import get_app_dir
                from src.stt.engine import download_parakeet_model

                self._fallback_dl_cancel = threading.Event()
                rec = getattr(self.daemon, "recognizer", None) if self.daemon is not None else None
                target = getattr(rec, "model_dir", None) or (get_app_dir() / "models" / "parakeet-tdt-0.6b-int8")
                download_parakeet_model(Path(target), progress_cb=on_progress, cancel_event=self._fallback_dl_cancel)
                if rec is not None and hasattr(rec, "reload_local_model"):
                    ok = bool(rec.reload_local_model())
                else:
                    ok = True
        except InterruptedError:
            ok = False
            err_msg = "Download canceled"
        except Exception as e:
            ok = False
            err_msg = f"Download failed: {e}"[:60]
        finally:
            self._fallback_dl_cancel = None
            self._post_ui(lambda: self._finish_model_download(ok, err_msg))

    def _finish_model_download(self, ok: bool, err_msg: str = "") -> None:
        self._model_downloading = False
        self._refresh_offline_model_ui()
        if ok:
            self._set_model_progress("Model ready!")
            if self._is_running and self.root is not None:
                self.root.after(2500, lambda: self._set_model_progress(""))
        elif err_msg:
            self._set_model_progress(err_msg)
        else:
            self._set_model_progress("")

    def _test_key(self) -> None:
        self.key_status.config(text="Testing…", fg=self.theme.on_surface_variant)
        key = self.key_entry.get().strip()
        threading.Thread(target=self._test_key_worker, args=(key,), daemon=True).start()

    def _test_key_worker(self, key: str) -> None:
        import requests

        try:
            r = requests.get(
                "https://openrouter.ai/api/v1/credits",
                headers={"Authorization": f"Bearer {key}"},
                timeout=15,
            )
            if r.status_code == 200:
                d = r.json().get("data", {})
                left = float(d.get("total_credits", 0)) - float(d.get("total_usage", 0))
                msg, color = f"Connected · ${left:.2f} credit left", self.theme.done
            else:
                msg, color = f"Rejected ({r.status_code})", self.theme.mic
        except Exception as e:
            msg, color = f"Could not reach OpenRouter: {e}"[:60], self.theme.mic
        if self.root:
            self.root.after(0, lambda: self.key_status.config(text=msg, fg=color))

    def _load_models(self) -> None:
        threading.Thread(target=self._load_models_worker, daemon=True).start()

    def _load_models_worker(self) -> None:
        import requests

        try:
            data = requests.get("https://openrouter.ai/api/v1/models", timeout=15).json()["data"]
            vision = [
                m
                for m in data
                if "image" in m.get("architecture", {}).get("input_modalities", [])
                and "text" in m.get("architecture", {}).get("output_modalities", [])
            ]
            vision.sort(key=lambda m: float(m.get("pricing", {}).get("prompt") or 0))
            ids = [m["id"] for m in vision]
            msg = f"Loaded {len(ids)} vision models, cheapest first"
        except Exception as e:
            ids, msg = None, f"Could not load models: {e}"[:60]

        def apply() -> None:
            if ids:
                self.model_box.config(values=ids)
            self.save_status.config(text=msg)

        if self.root:
            self.root.after(0, apply)

    def _save_settings(self) -> None:
        try:
            max_steps = max(1, min(30, int(self.max_steps_var.get().strip() or 8)))
        except ValueError:
            max_steps = 8
        self.max_steps_var.set(str(max_steps))

        base_url = self.base_entry.get().strip() or "https://openrouter.ai/api/v1"
        values = {
            "openrouter_api_key": self.key_entry.get().strip(),
            "vision_model": self.model_var.get(),
            "use_jev": bool(self.jev_var.get()),
            "audio_device": self.device_var.get(),
            "stt_cloud_model": VOICE_ENGINES.get(self.voice_var.get(), ""),
            "vision_api_base": base_url,
            "vision_api_key": self.vkey_entry.get().strip(),
            "theme": self.theme_var.get() if hasattr(self, "theme_var") else self.theme.name,
            "minimize_to_tray": bool(self.tray_var.get()) if hasattr(self, "tray_var") else self._tray_enabled,
            "max_vision_steps": max_steps,
        }
        save_settings(values)

        if values["theme"] != self.theme.name:
            self.set_theme(values["theme"])

        self._tray_enabled = values["minimize_to_tray"]
        if self._tray_enabled:
            self._ensure_tray()
        elif self._tray is not None:
            self._tray.stop()

        if self.daemon is not None:
            if getattr(self.daemon, "config", None) is not None:
                self.daemon.config.max_vision_steps = max_steps
            if getattr(self.daemon, "vision", None) is not None:
                base = base_url.rstrip("/")
                is_openrouter = "openrouter.ai" in base.lower()
                effective_key = values["vision_api_key"] or (values["openrouter_api_key"] if is_openrouter else "")
                self.daemon.vision.model_name = values["vision_model"]
                self.daemon.vision.api_key = effective_key
                self.daemon.vision.api_base = base
                # Local OpenAI-compatible endpoints (Ollama, LM Studio, vLLM) run keyless.
                self.daemon.vision.mock_mode = is_openrouter and not effective_key
            if getattr(self.daemon, "router", None) is not None:
                self.daemon.router.use_jev = values["use_jev"]
            if getattr(self.daemon, "recognizer", None) is not None:
                self.daemon.recognizer.cloud_model = values["stt_cloud_model"]
            dev = values["audio_device"]
            if getattr(self.daemon, "recorder", None) is not None:
                self.daemon.recorder.device_index = int(dev.split(":")[0]) if dev[:1].isdigit() else None

        self.save_status.config(text="Saved", fg=self.theme.success)
        if self.root:
            self.root.after(2200, lambda: self.save_status.config(text=""))
        self.log("Settings saved.")

    # ---------- dragging ----------

    def _drag_start(self, event) -> None:
        self._drag = (event.x_root - self._pos[0], event.y_root - self._pos[1])
        self._moved = False

    def _drag_move(self, event) -> None:
        self._moved = True
        x, y = event.x_root - self._drag[0], event.y_root - self._drag[1]
        self._pos = (x, y)
        self.root.geometry(f"+{x}+{y}")
