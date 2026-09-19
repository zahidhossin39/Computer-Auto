"""Floating HUD Pill overlay for real-time visual feedback."""

import tkinter as tk
from typing import Callable, Optional


class FloatingHUD:
    """A sleek, top-most, draggable status pill rendered via Tkinter on the main thread."""

    def __init__(
        self,
        on_toggle_click: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ):
        self.on_toggle_click = on_toggle_click
        self.on_close = on_close

        self.root: Optional[tk.Tk] = None
        self._is_running = False

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
        """Initialize the Tkinter window widgets."""
        self.root = tk.Tk()
        self.root.title("Computer-Auto HUD")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg="#000000")

        # Make black transparent on Windows
        try:
            self.root.wm_attributes("-transparentcolor", "#000000")
        except Exception:
            pass

        # Position at top-center of screen
        screen_w = self.root.winfo_screenwidth()
        pill_w = 480
        pill_h = 58
        start_x = (screen_w - pill_w) // 2
        start_y = 20
        self.root.geometry(f"{pill_w}x{pill_h}+{start_x}+{start_y}")

        # Rounded Pill Card
        self._pill_frame = tk.Frame(
            self.root,
            bg="#181825",
            highlightthickness=2,
            highlightbackground="#313244",
            cursor="hand2",
        )
        self._pill_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # Drag bindings
        for widget in (self.root, self._pill_frame):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

        # Content container
        content = tk.Frame(self._pill_frame, bg="#181825")
        content.pack(fill="both", expand=True, padx=12, pady=8)

        # Left status indicator dot
        self._dot_label = tk.Label(
            content,
            text="●",
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
            text="Ready — Double-Tap Ctrl or Click to Speak",
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

        # Action Button (Mic / Toggle)
        self._mic_btn = tk.Button(
            content,
            text="🎙️ Talk",
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

        # Close 'x' button
        close_btn = tk.Label(
            content,
            text="✕",
            font=("Segoe UI", 9),
            fg="#585b70",
            bg="#181825",
            cursor="hand2",
        )
        close_btn.pack(side="right", padx=(0, 4))
        close_btn.bind("<Button-1>", lambda e: self._handle_close())

        self._is_running = True

    def mainloop(self) -> None:
        """Run the main UI loop on the main thread."""
        if self.root:
            self.root.mainloop()

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
            if state == "listening":
                self._dot_label.config(text="●", fg="#f38ba8")  # Vibrant Red
                self._pill_frame.config(highlightbackground="#f38ba8")
                self._status_label.config(text=message, fg="#f38ba8")
                self._mic_btn.config(text="⏹️ Stop", bg="#f38ba8")
            elif state == "processing":
                self._dot_label.config(text="◌", fg="#f9e2af")  # Yellow
                self._pill_frame.config(highlightbackground="#f9e2af")
                self._status_label.config(text=message, fg="#f9e2af")
                self._mic_btn.config(text="⏳...", bg="#f9e2af")
            elif state == "executing":
                self._dot_label.config(text="⚡", fg="#89b4fa")  # Cyan / Blue
                self._pill_frame.config(highlightbackground="#89b4fa")
                self._status_label.config(text=message, fg="#89b4fa")
                self._mic_btn.config(text="⚡ Running", bg="#89b4fa")
            elif state == "guardrail":
                self._dot_label.config(text="⚠️", fg="#fab387")  # Peach/Orange
                self._pill_frame.config(highlightbackground="#fab387")
                self._status_label.config(text=message, fg="#fab387")
            else:  # ready
                self._dot_label.config(text="●", fg="#a6e3a1")  # Green
                self._pill_frame.config(highlightbackground="#313244")
                self._status_label.config(text=message, fg="#cdd6f4")
                self._mic_btn.config(text="🎙️ Talk", bg="#89b4fa")

            if detail:
                self._detail_label.config(text=detail)

        try:
            self.root.after(0, _apply)
        except Exception:
            pass
