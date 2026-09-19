"""Floating HUD Pill overlay for real-time visual feedback."""

import sys
import threading
import tkinter as tk
from typing import Callable, Optional


class FloatingHUD:
    """A sleek, top-most, draggable status pill rendered via Tkinter.

    Can run on the main thread (mainloop) or a dedicated thread (start_in_thread).
    """

    # Use a unique color key that won't clash with any UI element
    _TRANSPARENT_KEY = "#010101"

    def __init__(
        self,
        on_toggle_click: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ):
        self.on_toggle_click = on_toggle_click
        self.on_close = on_close

        self.root: Optional[tk.Tk] = None
        self._is_running = False
        self._thread: Optional[threading.Thread] = None

        # UI Elements
        self._pill_frame = None
        self._dot_label = None
        self._status_label = None
        self._detail_label = None
        self._mic_btn = None

        # Drag tracking
        self._drag_start_x = 0
        self._drag_start_y = 0

    def init_ui(self) -> None:
        """Initialize the Tkinter window and widgets. Must be called on the thread
        that will run mainloop()."""
        self.root = tk.Tk()
        self.root.title("Computer-Auto HUD")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)

        # Set a non-black background as the transparent key color
        self.root.configure(bg=self._TRANSPARENT_KEY)

        # Make the key color transparent on Windows
        try:
            self.root.wm_attributes("-transparentcolor", self._TRANSPARENT_KEY)
        except Exception:
            pass

        # Set alpha for Windows 11 compositing
        try:
            self.root.wm_attributes("-alpha", 0.97)
        except Exception:
            pass

        # Position at top-center of screen
        screen_w = self.root.winfo_screenwidth()
        pill_w = 480
        pill_h = 58
        start_x = (screen_w - pill_w) // 2
        start_y = 20
        self.root.geometry(f"{pill_w}x{pill_h}+{start_x}+{start_y}")

        # Build widgets
        self._build_pill()

        # Force window to appear on top
        self.root.deiconify()
        self.root.lift()
        self.root.update_idletasks()

        self._is_running = True
        print(f"[HUD] Pill created at ({start_x}, {start_y}), size {pill_w}x{pill_h}")

    def _build_pill(self) -> None:
        """Build the pill frame and all child widgets."""
        # Rounded Pill Card — use a solid dark background, NOT the transparent key
        self._pill_frame = tk.Frame(
            self.root,
            bg="#181825",
            highlightthickness=2,
            highlightbackground="#313244",
            cursor="hand2",
        )
        self._pill_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # Drag bindings on the pill frame only (root is transparent)
        self._pill_frame.bind("<ButtonPress-1>", self._start_drag)
        self._pill_frame.bind("<B1-Motion>", self._on_drag)

        # Content container
        content = tk.Frame(self._pill_frame, bg="#181825")
        content.pack(fill="both", expand=True, padx=12, pady=8)

        # Left status indicator dot
        self._dot_label = tk.Label(
            content,
            text="\u25CF",  # ●
            font=("Segoe UI", 16, "bold"),
            fg="#a6e3a1",  # Soft green
            bg="#181825",
        )
        self._dot_label.pack(side="left", padx=(0, 8))

        # Text column (Title + Subtext)
        text_col = tk.Frame(content, bg="#181825")
        text_col.pack(side="left", fill="both", expand=True)

        self._status_label = tk.Label(
            text_col,
            text="Ready \u2014 Double-Tap Ctrl or Click to Speak",
            font=("Segoe UI", 10, "bold"),
            fg="#cdd6f4",
            bg="#181825",
            anchor="w",
        )
        self._status_label.pack(fill="x")

        self._detail_label = tk.Label(
            text_col,
            text="Computer-Auto Voice Active",
            font=("Segoe UI", 8),
            fg="#6c7086",
            bg="#181825",
            anchor="w",
        )
        self._detail_label.pack(fill="x")

        # Close 'x' button (pack first so it's on the far right)
        close_btn = tk.Label(
            content,
            text="\u2715",  # ✕
            font=("Segoe UI", 9),
            fg="#585b70",
            bg="#181825",
            cursor="hand2",
        )
        close_btn.pack(side="right", padx=(0, 2))
        close_btn.bind("<Button-1>", lambda e: self._handle_close())

        # Action Button (Mic / Toggle)
        self._mic_btn = tk.Button(
            content,
            text="Talk",
            font=("Segoe UI", 9, "bold"),
            fg="#11111b",
            bg="#89b4fa",
            activebackground="#b4befe",
            relief="flat",
            padx=10,
            pady=2,
            cursor="hand2",
            command=self._on_btn_click,
        )
        self._mic_btn.pack(side="right", padx=(8, 4))

        # Make child widgets also draggable
        for w in (self._dot_label, self._status_label, self._detail_label):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

    def mainloop(self) -> None:
        """Run the main UI loop (blocks the calling thread)."""
        if self.root:
            self.root.mainloop()

    def start_in_thread(self) -> None:
        """Create the UI and run mainloop in a dedicated background thread."""
        def _run():
            self.init_ui()
            self.root.mainloop()
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def _start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_start_x)
        y = self.root.winfo_y() + (event.y - self._drag_start_y)
        self.root.geometry(f"+{x}+{y}")

    def _on_btn_click(self):
        if self.on_toggle_click:
            self.on_toggle_click()

    def _handle_close(self):
        if self.on_close:
            self.on_close()
        if self.root:
            self.root.quit()
            self.root.destroy()
            self._is_running = False

    def update_state(
        self, state: str, message: str, detail: str = ""
    ) -> None:
        """Thread-safe UI status update from background workers.
        state: 'ready' | 'listening' | 'processing' | 'executing' | 'guardrail' | 'error'
        """
        if not self.root or not self._is_running:
            return

        def _apply():
            if not self._is_running or not self.root:
                return
            try:
                if state == "listening":
                    self._dot_label.config(text="\u25CF", fg="#f38ba8")  # Red
                    self._pill_frame.config(highlightbackground="#f38ba8")
                    self._status_label.config(text=message, fg="#f38ba8")
                    self._mic_btn.config(text="Stop", bg="#f38ba8")
                elif state == "processing":
                    self._dot_label.config(text="\u25CC", fg="#f9e2af")  # Yellow
                    self._pill_frame.config(highlightbackground="#f9e2af")
                    self._status_label.config(text=message, fg="#f9e2af")
                    self._mic_btn.config(text="...", bg="#f9e2af")
                elif state == "executing":
                    self._dot_label.config(text="\u26A1", fg="#89b4fa")  # Blue
                    self._pill_frame.config(highlightbackground="#89b4fa")
                    self._status_label.config(text=message, fg="#89b4fa")
                    self._mic_btn.config(text="Running", bg="#89b4fa")
                elif state == "guardrail":
                    self._dot_label.config(text="\u26A0", fg="#fab387")  # Orange
                    self._pill_frame.config(highlightbackground="#fab387")
                    self._status_label.config(text=message, fg="#fab387")
                else:  # ready
                    self._dot_label.config(text="\u25CF", fg="#a6e3a1")  # Green
                    self._pill_frame.config(highlightbackground="#313244")
                    self._status_label.config(text=message, fg="#cdd6f4")
                    self._mic_btn.config(text="Talk", bg="#89b4fa")

                if detail:
                    self._detail_label.config(text=detail)
            except tk.TclError:
                pass  # Window already destroyed

        try:
            self.root.after(0, _apply)
        except Exception:
            pass
