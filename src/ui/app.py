"""Modern, fully-featured desktop application for Computer-Auto.

Provides a 100% visible, reliable GUI with real-time status monitoring,
speech transcription display, manual command execution, audio device selection,
subsystem diagnostics, and visual feedback for both Tier 1 and Tier 2 actions.
"""

import os
import sys
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Callable, Optional, Dict, Any

try:
    import sounddevice as sd
except ImportError:
    sd = None

from src.router.router import RouteResult


class DesktopApp:
    """The central visible desktop control center for Computer-Auto."""

    def __init__(
        self,
        daemon: Optional[Any] = None,
        on_toggle_listening: Optional[Callable[[], None]] = None,
        on_panic: Optional[Callable[[], None]] = None,
        on_run_command: Optional[Callable[[str], None]] = None,
        on_switch_to_hud: Optional[Callable[[], None]] = None,
    ):
        self.daemon = daemon
        self.on_toggle_listening = on_toggle_listening
        self.on_panic = on_panic
        self.on_run_command = on_run_command
        self.on_switch_to_hud = on_switch_to_hud

        self.root: Optional[tk.Tk] = None
        self._is_running = False
        self._always_on_top = True

        # State tracking
        self.current_state = "ready"
        self.current_message = "Ready — Double-tap Left Ctrl or click Start to speak"
        self.current_detail = "Parakeet STT (Offline) + Gemini Flash Vision active"

        # UI Widget references
        self._status_badge = None
        self._detail_label = None
        self._mic_btn = None
        self._hotkey_badge = None
        self._transcript_var = None
        self._cmd_entry = None
        self._route_label = None
        self._log_text = None
        self._device_combo = None
        self._gemini_badge = None

    def init_ui(self) -> None:
        """Create the window and all widgets on the current thread."""
        self.root = tk.Tk()
        self.root.title("Computer-Auto Control Center")
        self.root.geometry("820x740")
        self.root.minsize(760, 640)
        self.root.configure(bg="#1e1e2e")

        # Ensure window is on top if requested
        if self._always_on_top:
            self.root.wm_attributes("-topmost", True)

        # Center on screen
        self._center_window(820, 740)

        # Window styling
        self._apply_styles()

        # Build interface sections
        self._build_header()
        self._build_action_bar()
        self._build_speech_section()
        self._build_command_section()
        self._build_vision_and_audio_section()
        self._build_log_section()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Keyboard shortcuts inside window
        self.root.bind("<Escape>", lambda e: self._handle_panic())
        self.root.bind("<Return>", lambda e: self._handle_run_command())

        self._is_running = True
        self.log("UI Initialized successfully. App window is fully visible.")

        # Update initial state
        self._apply_state(self.current_state, self.current_message, self.current_detail)

    def _center_window(self, width: int, height: int) -> None:
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 2)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass

    def _apply_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TCombobox",
            fieldbackground="#313244",
            background="#45475a",
            foreground="#cdd6f4",
            arrowcolor="#cdd6f4",
        )

    def _build_header(self) -> None:
        header_frame = tk.Frame(self.root, bg="#181825", padx=16, pady=12)
        header_frame.pack(fill="x", side="top")

        # Top title row
        title_row = tk.Frame(header_frame, bg="#181825")
        title_row.pack(fill="x")

        title_lbl = tk.Label(
            title_row,
            text="Computer-Auto Control Center",
            font=("Segoe UI", 16, "bold"),
            fg="#cdd6f4",
            bg="#181825",
        )
        title_lbl.pack(side="left")

        # Switch to HUD button
        if self.on_switch_to_hud:
            hud_btn = tk.Button(
                title_row,
                text="Mini HUD Mode",
                font=("Segoe UI", 9),
                bg="#313244",
                fg="#cdd6f4",
                activebackground="#45475a",
                relief="flat",
                padx=8,
                pady=2,
                cursor="hand2",
                command=self.on_switch_to_hud,
            )
            hud_btn.pack(side="right", padx=(8, 0))

        # Always on top checkbutton
        top_var = tk.BooleanVar(value=self._always_on_top)

        def toggle_top():
            self._always_on_top = top_var.get()
            self.root.wm_attributes("-topmost", self._always_on_top)

        top_cb = tk.Checkbutton(
            title_row,
            text="Keep on Top",
            variable=top_var,
            command=toggle_top,
            bg="#181825",
            fg="#a6adc8",
            selectcolor="#313244",
            activebackground="#181825",
            activeforeground="#cdd6f4",
            font=("Segoe UI", 9),
        )
        top_cb.pack(side="right")

        # Status Banner Box
        banner_frame = tk.Frame(
            header_frame,
            bg="#313244",
            highlightthickness=1,
            highlightbackground="#45475a",
            padx=12,
            pady=8,
        )
        banner_frame.pack(fill="x", pady=(10, 0))

        status_top = tk.Frame(banner_frame, bg="#313244")
        status_top.pack(fill="x")

        self._status_badge = tk.Label(
            status_top,
            text="● READY",
            font=("Segoe UI", 11, "bold"),
            fg="#a6e3a1",
            bg="#313244",
            anchor="w",
        )
        self._status_badge.pack(side="left")

        self._hotkey_badge = tk.Label(
            status_top,
            text="Hotkey: Double-Tap Left Ctrl | Panic: Esc",
            font=("Segoe UI", 9),
            fg="#89b4fa",
            bg="#313244",
            anchor="e",
        )
        self._hotkey_badge.pack(side="right")

        self._detail_label = tk.Label(
            banner_frame,
            text=self.current_message,
            font=("Segoe UI", 9),
            fg="#cdd6f4",
            bg="#313244",
            anchor="w",
        )
        self._detail_label.pack(fill="x", pady=(4, 0))

    def _build_action_bar(self) -> None:
        action_frame = tk.Frame(self.root, bg="#1e1e2e", padx=16, pady=10)
        action_frame.pack(fill="x")

        # Big Mic / Talk Toggle Button
        self._mic_btn = tk.Button(
            action_frame,
            text="🎙️  Start Listening (Talk)",
            font=("Segoe UI", 12, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._handle_mic_click,
        )
        self._mic_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Panic Key Button
        panic_btn = tk.Button(
            action_frame,
            text="🛑  Panic Abort (Esc)",
            font=("Segoe UI", 11, "bold"),
            bg="#f38ba8",
            fg="#11111b",
            activebackground="#eba0ac",
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._handle_panic,
        )
        panic_btn.pack(side="right")

    def _build_speech_section(self) -> None:
        card = tk.Frame(
            self.root,
            bg="#181825",
            highlightthickness=1,
            highlightbackground="#313244",
            padx=14,
            pady=10,
        )
        card.pack(fill="x", padx=16, pady=(0, 8))

        top_row = tk.Frame(card, bg="#181825")
        top_row.pack(fill="x")

        lbl = tk.Label(
            top_row,
            text="Speech-to-Text Recognition (Parakeet TDT INT8)",
            font=("Segoe UI", 10, "bold"),
            fg="#cdd6f4",
            bg="#181825",
        )
        lbl.pack(side="left")

        # Test Mic Button
        test_mic_btn = tk.Button(
            top_row,
            text="⚡ Test Mic (2s)",
            font=("Segoe UI", 8, "bold"),
            bg="#313244",
            fg="#89dceb",
            activebackground="#45475a",
            relief="flat",
            padx=8,
            pady=1,
            cursor="hand2",
            command=self._test_mic_audio,
        )
        test_mic_btn.pack(side="right")

        # Transcript Display
        self._transcript_var = tk.StringVar(value="(Awaiting speech input...)")
        t_box = tk.Label(
            card,
            textvariable=self._transcript_var,
            font=("Segoe UI", 11, "italic"),
            fg="#f9e2af",
            bg="#11111b",
            padx=12,
            pady=8,
            anchor="w",
            relief="flat",
        )
        t_box.pack(fill="x", pady=(6, 0))

    def _build_command_section(self) -> None:
        card = tk.Frame(
            self.root,
            bg="#181825",
            highlightthickness=1,
            highlightbackground="#313244",
            padx=14,
            pady=10,
        )
        card.pack(fill="x", padx=16, pady=(0, 8))

        lbl = tk.Label(
            card,
            text="Manual Command Execution & Intent Routing",
            font=("Segoe UI", 10, "bold"),
            fg="#cdd6f4",
            bg="#181825",
        )
        lbl.pack(anchor="w")

        input_row = tk.Frame(card, bg="#181825")
        input_row.pack(fill="x", pady=(6, 0))

        self._cmd_entry = tk.Entry(
            input_row,
            font=("Segoe UI", 10),
            bg="#11111b",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#45475a",
        )
        self._cmd_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 8))
        self._cmd_entry.insert(0, "open notepad")

        run_btn = tk.Button(
            input_row,
            text="Execute",
            font=("Segoe UI", 9, "bold"),
            bg="#a6e3a1",
            fg="#11111b",
            activebackground="#94e2d5",
            relief="flat",
            padx=14,
            pady=3,
            cursor="hand2",
            command=self._handle_run_command,
        )
        run_btn.pack(side="right")

        # Route info
        self._route_label = tk.Label(
            card,
            text="Quick tests: 'open notepad' | 'volume up' | 'mute volume' | 'click center' (Vision)",
            font=("Segoe UI", 8),
            fg="#6c7086",
            bg="#181825",
            anchor="w",
        )
        self._route_label.pack(fill="x", pady=(4, 0))

    def _build_vision_and_audio_section(self) -> None:
        row_frame = tk.Frame(self.root, bg="#1e1e2e", padx=16)
        row_frame.pack(fill="x", pady=(0, 8))

        # Left Card: Audio Devices
        audio_card = tk.Frame(
            row_frame,
            bg="#181825",
            highlightthickness=1,
            highlightbackground="#313244",
            padx=10,
            pady=8,
        )
        audio_card.pack(side="left", fill="both", expand=True, padx=(0, 4))

        tk.Label(
            audio_card,
            text="Audio Input Device",
            font=("Segoe UI", 9, "bold"),
            fg="#cdd6f4",
            bg="#181825",
        ).pack(anchor="w")

        # Device combo
        devices = self._get_audio_input_devices()
        self._device_combo = ttk.Combobox(
            audio_card, values=devices, state="readonly", font=("Segoe UI", 8)
        )
        if devices:
            # Default to device [1] (USB mic) if available, else first device
            default_idx = 0
            for i, d in enumerate(devices):
                if d.startswith("[1]"):
                    default_idx = i
                    break
            self._device_combo.current(default_idx)
            # Immediately sync recorder device index
            self._apply_device_index(devices[default_idx])
        self._device_combo.pack(fill="x", pady=(4, 0))
        self._device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        # Right Card: Vision & Gemini Status
        vision_card = tk.Frame(
            row_frame,
            bg="#181825",
            highlightthickness=1,
            highlightbackground="#313244",
            padx=10,
            pady=8,
        )
        vision_card.pack(side="right", fill="both", expand=True, padx=(4, 0))

        v_top = tk.Frame(vision_card, bg="#181825")
        v_top.pack(fill="x")

        tk.Label(
            v_top,
            text="Tier 2 Gemini Vision",
            font=("Segoe UI", 9, "bold"),
            fg="#cdd6f4",
            bg="#181825",
        ).pack(side="left")

        # Test Screen Capture button
        test_cap_btn = tk.Button(
            v_top,
            text="Test Screen Grab",
            font=("Segoe UI", 8),
            bg="#313244",
            fg="#cba6f7",
            relief="flat",
            padx=6,
            pady=1,
            cursor="hand2",
            command=self._test_screen_capture,
        )
        test_cap_btn.pack(side="right")

        has_key = bool(os.environ.get("GEMINI_API_KEY"))
        key_status = "Gemini Flash Ready" if has_key else "GEMINI_API_KEY Missing"
        key_color = "#a6e3a1" if has_key else "#f38ba8"

        self._gemini_badge = tk.Label(
            vision_card,
            text=f"Status: {key_status} (gemini-2.5-flash)",
            font=("Segoe UI", 8),
            fg=key_color,
            bg="#181825",
            anchor="w",
        )
        self._gemini_badge.pack(fill="x", pady=(4, 0))

    def _build_log_section(self) -> None:
        log_frame = tk.Frame(self.root, bg="#1e1e2e", padx=16)
        log_frame.pack(fill="both", expand=True, pady=(0, 12))

        header_row = tk.Frame(log_frame, bg="#1e1e2e")
        header_row.pack(fill="x", pady=(0, 4))

        tk.Label(
            header_row,
            text="System Activity & Execution Log",
            font=("Segoe UI", 9, "bold"),
            fg="#a6adc8",
            bg="#1e1e2e",
        ).pack(side="left")

        clear_btn = tk.Button(
            header_row,
            text="Clear Log",
            font=("Segoe UI", 8),
            bg="#313244",
            fg="#6c7086",
            relief="flat",
            padx=6,
            pady=0,
            command=self._clear_log,
        )
        clear_btn.pack(side="right")

        self._log_text = scrolledtext.ScrolledText(
            log_frame,
            bg="#11111b",
            fg="#cdd6f4",
            font=("Consolas", 9),
            insertbackground="#cdd6f4",
            relief="flat",
            wrap="word",
        )
        self._log_text.pack(fill="both", expand=True)

    def _get_audio_input_devices(self) -> list:
        if sd is None:
            return ["sounddevice not available"]
        try:
            devices = []
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0:
                    devices.append(f"[{idx}] {dev['name']}")
            return devices or ["No input devices detected"]
        except Exception as e:
            return [f"Error querying devices: {e}"]

    def _apply_device_index(self, sel: str) -> None:
        """Parse and configure audio input device index on active recorder."""
        if not sel or "[" not in sel or "]" not in sel:
            return
        try:
            idx_str = sel.split("]")[0].replace("[", "").strip()
            idx = int(idx_str)
            if self.daemon and hasattr(self.daemon, "recorder"):
                self.daemon.recorder.device_index = idx
                self.log(f"Active recorder device index set to -> [{idx}]")
            elif hasattr(self, "_standalone_recorder"):
                self._standalone_recorder.device_index = idx
                self.log(f"Configured standalone recorder device index -> [{idx}]")
        except Exception as e:
            self.log(f"Could not configure device index: {e}")

    def _on_device_selected(self, event=None) -> None:
        sel = self._device_combo.get()
        self.log(f"Selected audio device: {sel}")
        self._apply_device_index(sel)

    def _handle_mic_click(self) -> None:
        if self.on_toggle_listening:
            self.on_toggle_listening()
        elif self.daemon:
            self.daemon.on_ui_toggle_click()

    def _handle_panic(self) -> None:
        self.log("[PANIC] Panic triggered by user.")
        if self.on_panic:
            self.on_panic()
        elif self.daemon:
            self.daemon.on_panic_key()

    def _handle_run_command(self) -> None:
        cmd = self._cmd_entry.get().strip()
        if not cmd:
            return
        self.log(f"[USER COMMAND]: \"{cmd}\"")
        if self.on_run_command:
            self.on_run_command(cmd)
        elif self.daemon:
            threading.Thread(
                target=self.daemon.handle_command, args=(cmd,), daemon=True
            ).start()
        else:
            # Standalone execution fallback
            def _standalone_run():
                try:
                    from src.config import load_config
                    from src.router.router import CommandRouter
                    from src.executor.windows import WindowsExecutor
                    cfg = load_config()
                    router = CommandRouter(intents=cfg.intents)
                    executor = WindowsExecutor()
                    route = router.route(cmd)
                    if not route.is_vision and route.intent is not None:
                        self.log(f"[ROUTER]: Matched intent '{route.intent.name}'")
                        if route.intent.action.type == "system_action" and route.intent.action.command:
                            executor.execute_system_action(route.intent.action.command)
                            self.log(f"[EXECUTED]: Dispatched '{route.intent.action.command}'")
                        elif route.intent.action.type == "launch_app":
                            executor.launch_app(route.intent.action)
                            self.log(f"[EXECUTED]: Launched '{route.intent.action.target}'")
                    else:
                        self.log(f"[ROUTER]: Unscripted command '{cmd}' routed to Tier 2 Vision")
                except Exception as e:
                    self.log(f"[ERROR]: {e}")
            threading.Thread(target=_standalone_run, daemon=True).start()

    def _test_mic_audio(self) -> None:
        self.log("[TEST]: Recording 2 seconds of audio for diagnostic...")
        self.update_state("listening", "Testing Microphone (2s)...", "Speak into your mic")

        def _worker():
            try:
                rec = None
                recog = None
                if self.daemon and hasattr(self.daemon, "recorder"):
                    rec = self.daemon.recorder
                    recog = self.daemon.recognizer
                else:
                    if not hasattr(self, "_standalone_recorder"):
                        from src.audio.recorder import AudioRecorder
                        from src.stt.engine import SpeechRecognizer
                        dev_idx = None
                        if self._device_combo:
                            try:
                                dev_idx = int(self._device_combo.get().split("]")[0].replace("[", "").strip())
                            except Exception:
                                pass
                        self._standalone_recorder = AudioRecorder(device_index=dev_idx)
                        self._standalone_recognizer = SpeechRecognizer()
                    rec = self._standalone_recorder
                    recog = self._standalone_recognizer

                # Record 2 seconds
                rec.start()
                if rec.last_error:
                    self.log(f"[AUDIO ERROR]: {rec.last_error}")
                    self.update_state("error", "Mic failed to open", rec.last_error)
                    return

                time.sleep(2.0)
                samples = rec.stop()

                import numpy as np
                max_amp = float(np.max(np.abs(samples))) if len(samples) > 0 else 0.0
                self.log(f"[TEST]: Captured {len(samples)} samples. Max Amplitude = {max_amp:.4f}")

                if max_amp < 0.005:
                    self.log("[TEST WARNING]: Audio signal level is very low or silent.")
                    self.update_state("ready", "Ready — Audio test silent", "Check mic volume or mute switch")
                    return

                self.update_state("processing", "Transcribing test audio...", "Running Parakeet STT")
                text = recog.transcribe(samples)
                self.log(f"[TEST TRANSCRIPTION]: \"{text or '(no speech recognized)'}\"")
                self.update_state("ready", f"Heard: \"{text}\"", "Microphone test passed!")
                self.set_transcript(text or "(Silence detected)")

            except Exception as e:
                self.log(f"[TEST ERROR]: {e}")
                self.update_state("error", "Test failed", str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _test_screen_capture(self) -> None:
        self.log("[TEST]: Testing Screen Capture...")

        def _worker():
            try:
                if self.daemon and hasattr(self.daemon, "capture"):
                    cap = self.daemon.capture
                else:
                    from src.vision.capture import ScreenCapture
                    cap = ScreenCapture()

                img, w, h = cap.grab_screen()
                self.log(f"[SCREEN CAPTURE SUCCESS]: Resolution {w}x{h}, Mode={img.mode}")
            except Exception as e:
                self.log(f"[SCREEN CAPTURE ERROR]: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _clear_log(self) -> None:
        if self._log_text:
            self._log_text.delete("1.0", tk.END)

    def _on_window_close(self) -> None:
        self.log("Closing application window...")
        self._is_running = False
        if self.daemon:
            self.daemon.shutdown()
        if self.root:
            self.root.quit()
            self.root.destroy()

    def log(self, message: str) -> None:
        """Thread-safe append message to log console."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"

        def _append():
            if self._log_text and self._is_running:
                try:
                    self._log_text.insert(tk.END, formatted)
                    self._log_text.see(tk.END)
                except tk.TclError:
                    pass

        if self.root and self._is_running:
            try:
                self.root.after(0, _append)
            except Exception:
                pass
        else:
            print(formatted.strip())

    def set_transcript(self, text: str) -> None:
        """Thread-safe update transcript label."""
        def _apply():
            if self._transcript_var:
                self._transcript_var.set(f"\"{text}\"")

        if self.root and self._is_running:
            try:
                self.root.after(0, _apply)
            except Exception:
                pass

    def update_state(self, state: str, message: str, detail: str = "") -> None:
        """Thread-safe update status banner and controls."""
        self.current_state = state
        self.current_message = message
        self.current_detail = detail

        if not self.root or not self._is_running:
            return

        def _apply():
            self._apply_state(state, message, detail)

        try:
            self.root.after(0, _apply)
        except Exception:
            pass

    def _apply_state(self, state: str, message: str, detail: str = "") -> None:
        if not self._is_running or not self.root:
            return

        try:
            if state == "listening":
                self._status_badge.config(text="● RECORDING AUDIO", fg="#f38ba8")
                self._detail_label.config(text=message, fg="#f38ba8")
                self._mic_btn.config(
                    text="⏹  Stop Listening (Processing...)",
                    bg="#f38ba8",
                    activebackground="#eba0ac",
                )
            elif state == "processing":
                self._status_badge.config(text="● TRANSCRIBING SPEECH", fg="#f9e2af")
                self._detail_label.config(text=message, fg="#f9e2af")
                self._mic_btn.config(
                    text="⏳  Transcribing Audio...",
                    bg="#f9e2af",
                    activebackground="#f9e2af",
                )
            elif state == "executing":
                self._status_badge.config(text="⚡ EXECUTING ACTION", fg="#89b4fa")
                self._detail_label.config(text=message, fg="#89b4fa")
                self._mic_btn.config(
                    text="⚡  Executing...",
                    bg="#89b4fa",
                    activebackground="#89b4fa",
                )
            elif state == "guardrail":
                self._status_badge.config(text="⚠️ CONFIRMATION REQUIRED", fg="#fab387")
                self._detail_label.config(text=message, fg="#fab387")
            elif state == "error":
                self._status_badge.config(text="❌ ERROR", fg="#f38ba8")
                self._detail_label.config(text=message, fg="#f38ba8")
            else:  # ready
                self._status_badge.config(text="● READY", fg="#a6e3a1")
                self._detail_label.config(text=message, fg="#cdd6f4")
                self._mic_btn.config(
                    text="🎙️  Start Listening (Talk)",
                    bg="#89b4fa",
                    activebackground="#b4befe",
                )

            if detail and self._route_label:
                self._route_label.config(text=detail)
        except tk.TclError:
            pass

    def mainloop(self) -> None:
        """Run Tkinter main event loop."""
        if self.root:
            self.root.mainloop()


if __name__ == "__main__":
    from pathlib import Path
    try:
        from dotenv import load_dotenv
        env_file = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_file.is_file():
            load_dotenv(dotenv_path=env_file)
    except Exception:
        pass

    print("Launching DesktopApp Control Center standalone...")
    app = DesktopApp()
    app.init_ui()
    app.mainloop()
