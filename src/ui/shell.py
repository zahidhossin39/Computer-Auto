"""The app shell: a small always-on-top pill that expands into the full panel.

Replaces the old fixed Control Center window. Two rules it exists to keep:
  - it never hides itself (hiding it during a vision run left the app invisible),
  - while the vision agent reads the screen it shrinks, fades and stops taking
    clicks, so it is never mistaken for a window to act on.
"""

import os
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional

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

# One palette, graphite with an indigo accent; every widget takes its colors from here.
# Tested with this app's set-of-marks prompt; "Load list" adds every OpenRouter vision model
VISION_MODELS = ["qwen/qwen3-vl-8b-instruct", "google/gemini-3.1-flash-lite",
                 "qwen/qwen3-vl-30b-a3b-instruct", "qwen/qwen3-vl-32b-instruct"]
VOICE_ENGINES = {  # label -> OpenRouter transcription model ("" = on-device)
    "On-device Parakeet (free, offline, ~0.5s)": "",
    "Cloud gpt-4o-transcribe (best with names, ~1.3s)": "openai/gpt-4o-transcribe",
    "Cloud gpt-4o-mini-transcribe (cheaper)": "openai/gpt-4o-mini-transcribe",
}

BG = "#14171D"          # window ground
PANEL = "#1B1F27"       # raised surface
PANEL_2 = "#232833"     # input/inset surface
LINE = "#2E3440"
INK = "#F2F4F8"
INK_2 = "#AEB6C6"
INK_3 = "#7C8496"
ACCENT = "#7C87FF"
MIC = "#FF6B70"
WORK = "#F0A92E"
DONE = "#40CE8D"
CHROMA = "#FF00FE"      # never drawn: the color Windows makes transparent

STATE_COLOR = {
    "ready": INK_3, "idle": INK_3, "listening": MIC, "processing": WORK,
    "executing": WORK, "done": DONE, "error": MIC, "guardrail": WORK,
}
STATE_WORD = {
    "ready": "Ready", "idle": "Ready", "listening": "Listening", "processing": "Understanding",
    "executing": "Working", "done": "Done", "error": "Needs you", "guardrail": "Needs you",
}
FONT = "Segoe UI"
PILL_H = 44
PANEL_W, PANEL_H = 560, 780


def _round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle: Tk has no primitive, and square corners read as a dialog."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class AppShell:
    """Pill-first control surface for the daemon."""

    def __init__(
        self,
        daemon: Optional[Any] = None,
        on_toggle_listening: Optional[Callable[[], None]] = None,
        on_panic: Optional[Callable[[], None]] = None,
        on_run_command: Optional[Callable[[str], None]] = None,
        on_switch_to_hud: Optional[Callable[[], None]] = None,  # kept for main.py compatibility
    ):
        self.daemon = daemon
        self.on_toggle_listening = on_toggle_listening
        self.on_panic = on_panic
        self.on_run_command = on_run_command

        self.root: Optional[tk.Tk] = None
        self._is_running = False
        self.expanded = False
        self.ghost = False
        self.current_state = "ready"
        self.current_message = "Ready"
        self.current_detail = "Double-tap Ctrl to talk"
        self._log_lines: list = []
        self._drag = (0, 0)

    # ---------- construction ----------

    def init_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("Computer-Auto")
        self.root.overrideredirect(True)  # our own chrome: a pill has no title bar
        self.root.configure(bg=CHROMA)
        self.root.attributes("-topmost", True)
        try:
            self.root.wm_attributes("-transparentcolor", CHROMA)  # rounded corners
        except Exception:
            self.root.configure(bg=BG)

        self.canvas = tk.Canvas(self.root, bg=CHROMA, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        for widget in (self.root, self.canvas):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        self._build_pill()
        self._build_panel()
        self._style_ttk()
        self._apply_state()
        self._layout_pill()

        self.root.bind("<Escape>", lambda e: self._panic())
        self._is_running = True
        self.log("Shell ready.")

    def _style_ttk(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=PANEL, foreground=INK)
        style.configure("Dark.TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=INK,
                        arrowcolor=INK_2, bordercolor=LINE, lightcolor=PANEL_2, darkcolor=PANEL_2)
        style.map("Dark.TCombobox", fieldbackground=[("readonly", PANEL_2)])
        self.root.option_add("*TCombobox*Listbox.background", PANEL_2)
        self.root.option_add("*TCombobox*Listbox.foreground", INK)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    # ---------- pill ----------

    def _build_pill(self) -> None:
        self.pill = tk.Frame(self.canvas, bg=PANEL)
        self.dot = tk.Canvas(self.pill, width=18, height=18, bg=PANEL, highlightthickness=0)
        self._dot_id = self.dot.create_oval(4, 4, 14, 14, fill=INK_3, outline="")
        self.dot.pack(side="left", padx=(2, 8))
        self.state_lbl = tk.Label(self.pill, text="Ready", bg=PANEL, fg=INK, font=(FONT, 10, "bold"))
        self.state_lbl.pack(side="left")
        self.detail_lbl = tk.Label(self.pill, text="", bg=PANEL, fg=INK_2, font=(FONT, 9))
        self.detail_lbl.pack(side="left", padx=(9, 0))
        self.step_lbl = tk.Label(self.pill, text="", bg=PANEL, fg=INK_3, font=(FONT, 8))
        self.step_lbl.pack(side="left", padx=(9, 0))
        for w in (self.pill, self.state_lbl, self.detail_lbl, self.dot, self.step_lbl):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._click_pill)
        self._pill_window = None

    def _layout_pill(self) -> None:
        """Size the window to the pill's own width; the pill grows with its text."""
        self.expanded = False
        self.canvas.delete("bg")
        self.panel.place_forget()
        self.pill.update_idletasks()
        w = max(190, self.pill.winfo_reqwidth() + 34)
        h = PILL_H
        self._place_window(w, h, bottom_right=True)
        self.canvas.config(width=w, height=h)
        _round_rect(self.canvas, 1, 1, w - 1, h - 1, h // 2, fill=PANEL, outline=LINE, tags="bg")
        if self._pill_window:
            self.canvas.delete(self._pill_window)
        self._pill_window = self.canvas.create_window(17, h // 2, window=self.pill, anchor="w")

    def _click_pill(self, _event=None) -> None:
        if self._moved or self.ghost:
            return
        self._expand()

    # ---------- panel ----------

    def _build_panel(self) -> None:
        self.panel = tk.Frame(self.canvas, bg=PANEL)

        head = tk.Frame(self.panel, bg=PANEL)
        head.pack(fill="x", padx=16, pady=(13, 9))
        tk.Label(head, text="Computer-Auto", bg=PANEL, fg=INK, font=(FONT, 12, "bold")).pack(side="left")
        tk.Label(head, text="Esc stops everything", bg=PANEL, fg=INK_3, font=(FONT, 8)).pack(side="left", padx=(10, 0))
        self._chip(head, "Collapse", self._collapse).pack(side="right")
        self._chip(head, "Quit", self._quit).pack(side="right", padx=(0, 6))
        for w in (head,):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        # big primary controls
        bar = tk.Frame(self.panel, bg=PANEL)
        bar.pack(fill="x", padx=16)
        self.mic_btn = tk.Button(bar, text="Start listening", command=self._toggle, relief="flat",
                                 bg=ACCENT, fg="#0B0D11", activebackground=ACCENT, activeforeground="#0B0D11",
                                 font=(FONT, 10, "bold"), cursor="hand2", bd=0, pady=9)
        self.mic_btn.pack(side="left", fill="x", expand=True)
        tk.Button(bar, text="Stop", command=self._panic, relief="flat", bg=PANEL_2, fg=MIC,
                  activebackground=PANEL_2, activeforeground=MIC, font=(FONT, 10, "bold"),
                  cursor="hand2", bd=0, padx=18, pady=9).pack(side="left", padx=(8, 0))

        tabrow = tk.Frame(self.panel, bg=PANEL)
        tabrow.pack(fill="x", padx=16, pady=(14, 0))
        body = tk.Frame(self.panel, bg=PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=(8, 10))

        self._tabs = {}
        self._panes = {}
        for name in ("Activity", "Settings", "Commands"):
            holder = tk.Frame(tabrow, bg=PANEL)
            holder.pack(side="left", padx=(0, 4))
            btn = tk.Label(holder, text=name, bg=PANEL, fg=INK_3, font=(FONT, 9), cursor="hand2",
                           padx=8, pady=4)
            btn.pack()
            rule = tk.Frame(holder, bg=PANEL, height=2)
            rule.pack(fill="x")
            btn.bind("<Button-1>", lambda e, n=name: self._show_tab(n))
            pane = tk.Frame(body, bg=PANEL)
            self._tabs[name] = (btn, rule)
            self._panes[name] = pane

        self._build_activity(self._panes["Activity"])
        self._build_settings(self._panes["Settings"])
        self._build_commands(self._panes["Commands"])
        self._show_tab("Activity")

    def _show_tab(self, name: str) -> None:
        for other, (btn, rule) in self._tabs.items():
            on = other == name
            btn.config(fg=INK if on else INK_3, font=(FONT, 9, "bold") if on else (FONT, 9))
            rule.config(bg=ACCENT if on else PANEL)
            self._panes[other].pack_forget()
        self._panes[name].pack(fill="both", expand=True)

    def _chip(self, parent, text, command) -> tk.Button:
        return tk.Button(parent, text=text, command=command, relief="flat", bg=PANEL_2, fg=INK_2,
                         activebackground=LINE, activeforeground=INK, font=(FONT, 8), cursor="hand2",
                         bd=0, padx=10, pady=3)

    def _label(self, parent, text, **kw) -> tk.Label:
        return tk.Label(parent, text=text, bg=PANEL, fg=kw.pop("fg", INK_2), anchor="w",
                        font=kw.pop("font", (FONT, 9)), **kw)

    def _dropdown(self, parent, var: "tk.StringVar", values: list) -> tk.OptionMenu:
        menu = tk.OptionMenu(parent, var, *values)
        menu.config(bg=PANEL_2, fg=INK, activebackground=LINE, activeforeground=INK, relief="flat",
                    highlightthickness=1, highlightbackground=LINE, font=(FONT, 9), anchor="w",
                    direction="below", pady=5)
        menu["menu"].config(bg=PANEL_2, fg=INK, activebackground=ACCENT, activeforeground="#0B0D11",
                            font=(FONT, 9), relief="flat", bd=0)
        return menu

    def _entry(self, parent, show=None) -> tk.Entry:
        e = tk.Entry(parent, bg=PANEL_2, fg=INK, insertbackground=INK, relief="flat",
                     font=(FONT, 10), show=show)
        e.configure(highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT)
        return e

    def _build_activity(self, tab) -> None:
        self._label(tab, "Type a command", font=(FONT, 8)).pack(fill="x", padx=6, pady=(10, 4))
        row = tk.Frame(tab, bg=PANEL)
        row.pack(fill="x", padx=6)
        self.cmd_entry = self._entry(row)
        self.cmd_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.cmd_entry.bind("<Return>", lambda e: self._run_typed())
        tk.Button(row, text="Run", command=self._run_typed, relief="flat", bg=PANEL_2, fg=INK,
                  activebackground=LINE, activeforeground=INK, font=(FONT, 9, "bold"),
                  cursor="hand2", bd=0, padx=14).pack(side="left", padx=(8, 0), ipady=5)

        self.transcript = self._label(tab, "", fg=INK_3, font=(FONT, 9, "italic"))
        self.transcript.pack(fill="x", padx=6, pady=(9, 4))

        self.log_text = tk.Text(tab, bg=PANEL_2, fg=INK_2, relief="flat", font=("Consolas", 8),
                                height=10, wrap="word", padx=10, pady=8, state="disabled")
        self.log_text.configure(highlightthickness=1, highlightbackground=LINE)
        self.log_text.pack(fill="both", expand=True, padx=6, pady=(4, 8))

    def _build_settings(self, tab) -> None:
        s = load_settings()
        pad = {"padx": 6}

        self._label(tab, "OpenRouter API key", font=(FONT, 8)).pack(fill="x", pady=(10, 4), **pad)
        row = tk.Frame(tab, bg=PANEL)
        row.pack(fill="x", **pad)
        self.key_entry = self._entry(row, show="•")
        # Fall back to the key already in the environment/.env so the field is never blank
        self.key_entry.insert(0, s.get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY", ""))
        self.key_entry.pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(row, text="Test", command=self._test_key, relief="flat", bg=PANEL_2, fg=INK,
                  activebackground=LINE, activeforeground=INK, font=(FONT, 9), cursor="hand2",
                  bd=0, padx=12).pack(side="left", padx=(8, 0), ipady=5)
        self.key_status = self._label(tab, "Not tested yet", fg=INK_3, font=(FONT, 8))
        self.key_status.pack(fill="x", pady=(5, 0), **pad)

        self._label(tab, "Vision model (type any id, or load the full list)",
                    font=(FONT, 8)).pack(fill="x", pady=(12, 4), **pad)
        row = tk.Frame(tab, bg=PANEL)
        row.pack(fill="x", **pad)
        self.model_var = tk.StringVar(value=s.get("vision_model", "qwen/qwen3-vl-8b-instruct"))
        self.model_box = ttk.Combobox(row, textvariable=self.model_var, values=VISION_MODELS,
                                      font=(FONT, 9), style="Dark.TCombobox")
        self.model_box.pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(row, text="Load list", command=self._load_models, relief="flat", bg=PANEL_2, fg=INK,
                  activebackground=LINE, activeforeground=INK, font=(FONT, 9), cursor="hand2",
                  bd=0, padx=12).pack(side="left", padx=(8, 0), ipady=4)

        self._label(tab, "Vision endpoint (OpenAI-compatible) and key (blank = OpenRouter key)",
                    font=(FONT, 8)).pack(fill="x", pady=(12, 4), **pad)
        row = tk.Frame(tab, bg=PANEL)
        row.pack(fill="x", **pad)
        self.base_entry = self._entry(row)
        self.base_entry.insert(0, s.get("vision_api_base") or "https://openrouter.ai/api/v1")
        self.base_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.vkey_entry = self._entry(row, show="•")
        self.vkey_entry.insert(0, s.get("vision_api_key", ""))
        self.vkey_entry.pack(side="left", padx=(8, 0), ipady=5)

        self._label(tab, "Voice recognition", font=(FONT, 8)).pack(fill="x", pady=(12, 4), **pad)
        current = s.get("stt_cloud_model", "")
        self.voice_var = tk.StringVar(value=next((k for k, v in VOICE_ENGINES.items() if v == current),
                                                 list(VOICE_ENGINES)[0]))
        self._dropdown(tab, self.voice_var, list(VOICE_ENGINES)).pack(fill="x", **pad)

        self.jev_var = tk.BooleanVar(value=s.get("use_jev", True))
        tk.Checkbutton(tab, text="Use Jev to understand unusual wording (~0.7s, $0.00003)",
                       variable=self.jev_var, bg=PANEL, fg=INK_2, selectcolor=PANEL_2,
                       activebackground=PANEL, activeforeground=INK, font=(FONT, 9),
                       anchor="w", bd=0, highlightthickness=0).pack(fill="x", pady=(12, 0), **pad)

        self._label(tab, "Microphone", font=(FONT, 8)).pack(fill="x", pady=(14, 4), **pad)
        self.device_var = tk.StringVar(value=s.get("audio_device", "System default"))
        self._dropdown(tab, self.device_var, self._input_devices()).pack(fill="x", **pad)

        save_row = tk.Frame(tab, bg=PANEL)
        save_row.pack(fill="x", pady=(16, 8), **pad)
        tk.Button(save_row, text="Save", command=self._save_settings, relief="flat", bg=ACCENT,
                  fg="#0B0D11", activebackground=ACCENT, activeforeground="#0B0D11",
                  font=(FONT, 9, "bold"), cursor="hand2", bd=0, padx=18, pady=6).pack(side="left")
        self.save_status = self._label(save_row, "", fg=DONE, font=(FONT, 8))
        self.save_status.pack(side="left", padx=(10, 0))

    def _build_commands(self, tab) -> None:
        box = tk.Text(tab, bg=PANEL, fg=INK_2, relief="flat", font=(FONT, 9), wrap="word",
                      padx=8, pady=8, state="normal", highlightthickness=0)
        intents = getattr(getattr(self.daemon, "config", None), "intents", []) or []
        box.insert("end", "Say it your way\n", "cmd")
        box.insert("end", "    open <any installed app>  ·  type <text>  ·  go to <site.com>  ·  google <query>\n"
                          "    chain them: open notepad and type hello\n\n", "alt")
        if intents:
            for intent in intents:
                box.insert("end", f"{intent.triggers[0]}\n", "cmd")
                box.insert("end", f"    {', '.join(intent.triggers[1:4]) or 'instant'}\n", "alt")
        else:
            box.insert("end", "Commands load with the app.")
        box.tag_configure("cmd", foreground=INK, font=(FONT, 9, "bold"))
        box.tag_configure("alt", foreground=INK_3, font=(FONT, 8))
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=6, pady=8)
        self._label(tab, "Anything else is understood by Jev, then done on screen.",
                    fg=INK_3, font=(FONT, 8)).pack(fill="x", padx=6, pady=(0, 8))

    # ---------- expand / collapse / ghost ----------

    def _place_window(self, w: int, h: int, bottom_right: bool = False) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if bottom_right or not hasattr(self, "_pos"):
            x, y = screen_w - w - 28, screen_h - h - 70
        else:
            x, y = self._pos
            x = min(max(0, x), screen_w - w)
            y = min(max(0, y), screen_h - h)
        self._pos = (x, y)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _expand(self) -> None:
        self.expanded = True
        w, h = PANEL_W, PANEL_H
        x = min(self._pos[0], self.root.winfo_screenwidth() - w - 20)
        y = min(self._pos[1], self.root.winfo_screenheight() - h - 50)
        self._pos = (max(20, x), max(20, y))
        self.root.geometry(f"{w}x{h}+{self._pos[0]}+{self._pos[1]}")
        self.canvas.config(width=w, height=h)
        self.canvas.delete("bg")
        if self._pill_window:
            self.canvas.delete(self._pill_window)
            self._pill_window = None
        _round_rect(self.canvas, 1, 1, w - 1, h - 1, 16, fill=PANEL, outline=LINE, tags="bg")
        self.panel.place(x=8, y=8, width=w - 16, height=h - 16)

    def _collapse(self) -> None:
        self._layout_pill()

    def set_ghost(self, on: bool) -> None:
        """Vision run: shrink, fade and stop taking clicks. Never hide."""
        if self.root is None:
            return
        self.ghost = on
        self.root.after(0, self._apply_ghost, on)
        time.sleep(0.2)  # let the window actually redraw before the screenshot

    def _apply_ghost(self, on: bool) -> None:
        if on and self.expanded:
            self._layout_pill()
        try:
            self.root.attributes("-alpha", 0.5 if on else 1.0)
        except Exception:
            pass
        self._set_click_through(on)

    def _set_click_through(self, on: bool) -> None:
        """Clicks pass to the window underneath while we are ghosted."""
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
        if self.root:
            self.root.after(0, self._apply_state)

    def _apply_state(self) -> None:
        color = STATE_COLOR.get(self.current_state, INK_3)
        word = STATE_WORD.get(self.current_state, self.current_message[:18])
        self.dot.itemconfig(self._dot_id, fill=color)
        self.state_lbl.config(text=word, fg=INK)
        detail = self.current_detail or self.current_message
        self.detail_lbl.config(text=detail[:46])
        step = ""
        if self.current_message.lower().startswith("vision step"):
            step = self.current_message.replace("Vision step", "Step").split(":")[0]
        self.step_lbl.config(text=step)
        if hasattr(self, "mic_btn"):
            listening = self.current_state == "listening"
            self.mic_btn.config(text="Stop listening" if listening else "Start listening",
                                bg=MIC if listening else ACCENT)
        if not self.expanded and not self.ghost:
            self._layout_pill()

    def log(self, message: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')}  {message}"
        self._log_lines.append(line)
        if self.root and hasattr(self, "log_text"):
            self.root.after(0, self._append_log, line)

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
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

    def _run_typed(self) -> None:
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        self.cmd_entry.delete(0, "end")  # clear, so the next command is not appended
        if self.on_run_command:
            self.on_run_command(cmd)

    def _quit(self) -> None:
        if self.daemon and hasattr(self.daemon, "shutdown"):
            self.daemon.shutdown()
        if self.root:
            self.root.destroy()

    def _input_devices(self) -> list:
        names = ["System default"]
        if sd is not None:
            try:
                for i, d in enumerate(sd.query_devices()):
                    if d.get("max_input_channels", 0) > 0:
                        names.append(f"{i}: {d['name'][:40]}")
            except Exception:
                pass
        return names

    def _test_key(self) -> None:
        self.key_status.config(text="Testing…", fg=INK_3)
        threading.Thread(target=self._test_key_worker, daemon=True).start()

    def _test_key_worker(self) -> None:
        import requests
        key = self.key_entry.get().strip()
        try:
            r = requests.get("https://openrouter.ai/api/v1/credits",
                             headers={"Authorization": f"Bearer {key}"}, timeout=15)
            if r.status_code == 200:
                d = r.json().get("data", {})
                left = float(d.get("total_credits", 0)) - float(d.get("total_usage", 0))
                msg, color = f"Connected · ${left:.2f} credit left", DONE
            else:
                msg, color = f"Rejected ({r.status_code})", MIC
        except Exception as e:
            msg, color = f"Could not reach OpenRouter: {e}"[:60], MIC
        self.root.after(0, lambda: self.key_status.config(text=msg, fg=color))

    def _load_models(self) -> None:
        threading.Thread(target=self._load_models_worker, daemon=True).start()

    def _load_models_worker(self) -> None:
        """Every OpenRouter model that accepts images, cheapest first."""
        import requests
        try:
            data = requests.get("https://openrouter.ai/api/v1/models", timeout=15).json()["data"]
            vision = [m for m in data if "image" in m.get("architecture", {}).get("input_modalities", [])
                      and "text" in m.get("architecture", {}).get("output_modalities", [])]
            vision.sort(key=lambda m: float(m.get("pricing", {}).get("prompt") or 0))
            ids = [m["id"] for m in vision]
            msg = f"Loaded {len(ids)} vision models, cheapest first"
        except Exception as e:
            ids, msg = None, f"Could not load models: {e}"[:60]
        def apply():
            if ids:
                self.model_box.config(values=ids)
            self.save_status.config(text=msg)
        self.root.after(0, apply)

    def _save_settings(self) -> None:
        values = {
            "openrouter_api_key": self.key_entry.get().strip(),
            "vision_model": self.model_var.get(),
            "use_jev": bool(self.jev_var.get()),
            "audio_device": self.device_var.get(),
            "stt_cloud_model": VOICE_ENGINES[self.voice_var.get()],
            "vision_api_base": self.base_entry.get().strip() or "https://openrouter.ai/api/v1",
            "vision_api_key": self.vkey_entry.get().strip(),
        }
        save_settings(values)
        # Apply without a restart where the daemon allows it
        if self.daemon is not None:
            if getattr(self.daemon, "vision", None) is not None:
                self.daemon.vision.model_name = values["vision_model"]
                self.daemon.vision.api_key = (values["vision_api_key"] or values["openrouter_api_key"]
                                              or self.daemon.vision.api_key)
                self.daemon.vision.api_base = values["vision_api_base"].rstrip("/")
                self.daemon.vision.mock_mode = not self.daemon.vision.api_key
            if getattr(self.daemon, "router", None) is not None:
                self.daemon.router.use_jev = values["use_jev"]
            if getattr(self.daemon, "recognizer", None) is not None:
                self.daemon.recognizer.cloud_model = values["stt_cloud_model"]
            dev = values["audio_device"]
            if getattr(self.daemon, "recorder", None) is not None:
                self.daemon.recorder.device_index = int(dev.split(":")[0]) if dev[:1].isdigit() else None
        self.save_status.config(text="Saved")
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
