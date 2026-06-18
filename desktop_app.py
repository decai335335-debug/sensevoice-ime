import ctypes
import os
import queue
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from pathlib import Path


def add_external_venv_site_packages():
    """Let the desktop EXE use the portable .venv beside it."""
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, *exe_dir.parents])
    script_dir = Path(__file__).resolve().parent
    candidates.extend([script_dir, *script_dir.parents])
    for base in candidates:
        for env_name in (".venv", "venv"):
            site_packages = base / env_name / "Lib" / "site-packages"
            if site_packages.exists():
                site_path = str(site_packages)
                if site_path not in sys.path:
                    sys.path.insert(0, site_path)
                return


add_external_venv_site_packages()
import sensevoice_ime as core


INSTANCE_MUTEX = None
INSTANCE_SOCKET = None


def app_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_ROOT = app_root()
core.CONFIG_PATH = APP_ROOT / "config.json"
core.PHRASES_PATH = APP_ROOT / "phrases.json"
core.RAW_TRANSCRIPTS_PATH = APP_ROOT / "raw_transcripts.jsonl"


def dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def set_app_user_model_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SenseVoiceIME.Desktop")
    except Exception:
        pass


def apply_window_icons(root):
    try:
        root.iconbitmap(str(APP_ICON))
    except Exception:
        pass
    try:
        root.iconphoto(True, tk.PhotoImage(file=str(APP_ICON.with_suffix(".png"))))
    except Exception:
        pass
    try:
        hwnd = root.winfo_id()
        image_icon = 1
        load_from_file = 0x10
        lr_default_size = 0x40
        large_icon = ctypes.windll.user32.LoadImageW(
            None, str(APP_ICON), image_icon, 32, 32, load_from_file | lr_default_size
        )
        small_icon = ctypes.windll.user32.LoadImageW(
            None, str(APP_ICON), image_icon, 16, 16, load_from_file | lr_default_size
        )
        wm_seticon = 0x0080
        if large_icon:
            ctypes.windll.user32.SendMessageW(hwnd, wm_seticon, 1, large_icon)
        if small_icon:
            ctypes.windll.user32.SendMessageW(hwnd, wm_seticon, 0, small_icon)
    except Exception:
        pass


def ensure_single_instance():
    global INSTANCE_MUTEX, INSTANCE_SOCKET
    try:
        INSTANCE_SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        INSTANCE_SOCKET.bind(("127.0.0.1", 18765))
        INSTANCE_SOCKET.listen(1)
        return True
    except OSError:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, "Local\\SenseVoiceIMEDesktopApp")
        if kernel32.GetLastError() == 183:
            return False
    except Exception:
        pass
    return True


BG = "#f5f7f8"
SURFACE = "#ffffff"
SURFACE_2 = "#edf3f3"
TEXT = "#172022"
MUTED = "#657276"
ACCENT = "#0f9f8f"
DANGER = "#df3f47"
WARNING = "#e69b2f"
LINE = "#dfe7e8"
LOG_BG = "#101416"
LOG_FG = "#dfe7e8"
APP_ICON = APP_ROOT / "assets" / "sensevoice.ico"
FONT_UI = "Microsoft YaHei UI"
FONT_LATIN = "Segoe UI"


T = {
    "ready": "\u51c6\u5907\u5c31\u7eea",
    "waiting": "\u7b49\u5f85\u5feb\u6377\u952e",
    "recording": "\u6b63\u5728\u5f55\u97f3",
    "voice_input": "\u58f0\u97f3\u8f93\u5165\u4e2d",
    "processing": "\u8bc6\u522b\u4e2d",
    "please_wait": "\u8bf7\u7a0d\u5019",
    "done": "\u5b8c\u6210",
    "text_output": "\u6587\u672c\u5df2\u8f93\u51fa",
}


class TextRedirector:
    def __init__(self, event_queue, stream_name):
        self.event_queue = event_queue
        self.stream_name = stream_name

    def write(self, text):
        if text:
            self.event_queue.put(("log", text))

    def flush(self):
        pass


class ScrollFrame(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = tk.Frame(self.canvas, bg=BG)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", self.on_content_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

    def on_content_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class FloatingWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.iconbitmap(str(APP_ICON))
        except Exception:
            pass
        self.configure(bg="#12181b")
        self.status = "idle"
        self.drag = None
        self.geometry("286x112+120+120")

        self.card = tk.Frame(self, bg="#12181b", padx=16, pady=14)
        self.card.pack(fill="both", expand=True)
        self.card.bind("<ButtonPress-1>", self.start_drag)
        self.card.bind("<B1-Motion>", self.on_drag)

        self.wave = tk.Canvas(self.card, width=92, height=50, bg="#12181b", highlightthickness=0)
        self.wave.pack(side="left")
        copy = tk.Frame(self.card, bg="#12181b")
        copy.pack(side="left", padx=(10, 0))

        self.title_label = tk.Label(copy, text=T["ready"], fg="white", bg="#12181b", font=(FONT_UI, 13, "bold"))
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(copy, text=T["waiting"], fg="#a8b0b3", bg="#12181b", font=(FONT_UI, 11))
        self.subtitle_label.pack(anchor="w", pady=(4, 0))
        self.phase = 0
        self.after(80, self.animate)
        self.after(600, self.keep_on_top)

    def start_drag(self, event):
        self.drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def on_drag(self, event):
        if self.drag:
            self.geometry(f"+{event.x_root - self.drag[0]}+{event.y_root - self.drag[1]}")

    def set_state(self, payload):
        status = payload.get("status", "idle")
        self.status = status
        labels = {
            "idle": (T["ready"], T["waiting"]),
            "recording": (T["recording"], T["voice_input"]),
            "processing": (T["processing"], T["please_wait"]),
            "done": (T["done"], T["text_output"]),
        }
        title, subtitle = labels.get(status, labels["idle"])
        self.title_label.configure(text=payload.get("title", title))
        self.subtitle_label.configure(text=payload.get("subtitle", payload.get("hint", subtitle)))
        if status in {"recording", "processing", "done"}:
            self.deiconify()
        elif status == "idle":
            self.after(700, self.withdraw)

    def animate(self):
        self.wave.delete("all")
        color = ACCENT
        if self.status == "recording":
            color = DANGER
        elif self.status == "processing":
            color = WARNING
        heights = [14, 24, 34, 20, 30, 18, 28]
        for index, base in enumerate(heights):
            height = base * 0.45 if self.status == "idle" else 10 + ((base + self.phase * 5 + index * 7) % 30)
            x = 7 + index * 10
            self.wave.create_line(x, 22 - height / 2, x, 22 + height / 2, width=5, fill=color, capstyle="round")
        self.phase = (self.phase + 1) % 12
        self.after(90, self.animate)

    def keep_on_top(self):
        try:
            if self.winfo_viewable():
                self.attributes("-topmost", False)
                self.attributes("-topmost", True)
                self.lift()
        except Exception:
            pass
        self.after(900, self.keep_on_top)


class DesktopApp:
    def __init__(self):
        set_app_user_model_id()
        dpi_awareness()
        self.root = tk.Tk()
        self.root.title("SenseVoice IME")
        apply_window_icons(self.root)
        self.root.geometry("1240x840")
        self.root.minsize(1040, 720)
        self.root.configure(bg=BG)
        self.root.tk.call("tk", "scaling", 1.18)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.config = core.load_config()
        self.disable_prompts()
        self.app = None
        self.ready = False
        self.closing = False
        self.app_thread = None
        self.event_queue = queue.Queue()
        self.controls = {}
        self.command_buttons = []
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = TextRedirector(self.event_queue, "stdout")
        sys.stderr = TextRedirector(self.event_queue, "stderr")

        self.float_window = FloatingWindow(self.root)
        self.build_ui()
        self.refresh_config_ui()
        self.set_controls_enabled(False)
        self.root.after(120, self.drain_events)

    def disable_prompts(self):
        self.config["prompt_audio_processing_on_start"] = False
        self.config["prompt_noise_suppression_on_start"] = False
        self.config["prompt_asr_device_on_start"] = False
        self.config["prompt_asr_engine_on_start"] = False
        self.config["prompt_text_optimizer_on_start"] = False

    def build_ui(self):
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)

        sidebar = tk.Frame(shell, bg=SURFACE, width=318, padx=24, pady=28)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=SURFACE)
        brand.pack(fill="x", pady=(0, 24))
        tk.Label(brand, text="SV", fg="white", bg=ACCENT, width=4, height=2, font=(FONT_LATIN, 13, "bold")).pack(side="left")
        tk.Label(brand, text="SenseVoice IME", fg=TEXT, bg=SURFACE, font=(FONT_LATIN, 15, "bold")).pack(anchor="w", padx=(14, 0))
        tk.Label(brand, text="Desktop speech input", fg=MUTED, bg=SURFACE, font=(FONT_LATIN, 12)).pack(anchor="w", padx=(14, 0))

        self.hotkey_label = tk.Label(sidebar, text="", justify="left", fg=TEXT, bg=SURFACE, font=(FONT_UI, 11))
        self.hotkey_label.pack(fill="x", pady=(0, 18))
        self.update_hotkey_label()

        self.status_card = tk.Frame(sidebar, bg=SURFACE_2, padx=14, pady=14, highlightbackground=LINE, highlightthickness=1)
        self.status_card.pack(side="bottom", fill="x")
        self.status_dot = tk.Canvas(self.status_card, width=18, height=18, bg=SURFACE_2, highlightthickness=0)
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(self.status_card, text="\u5f85\u547d\u4e2d\n\u5148\u542f\u52a8\u8bed\u97f3\u5f15\u64ce", justify="left", fg=TEXT, bg=SURFACE_2, font=(FONT_UI, 12, "bold"))
        self.status_text.pack(side="left", padx=(8, 0))

        scroll = ScrollFrame(shell)
        scroll.pack(side="left", fill="both", expand=True)
        main = tk.Frame(scroll.content, bg=BG, padx=30, pady=28)
        main.pack(fill="both", expand=True)

        tk.Label(main, text="WINDOWS VOICE INPUT", fg=MUTED, bg=BG, font=(FONT_LATIN, 11, "bold")).pack(anchor="w")
        tk.Label(main, text="\u8bed\u97f3\u8f93\u5165\u63a7\u5236\u53f0", fg=TEXT, bg=BG, font=(FONT_UI, 32, "bold")).pack(anchor="w", pady=(4, 20))

        hero = self.panel(main, padx=28, pady=24)
        hero.pack(fill="x")
        self.hero_title = tk.Label(hero, text=T["ready"], fg=TEXT, bg=SURFACE, font=(FONT_UI, 42, "bold"))
        self.hero_title.pack(anchor="w")
        self.hero_copy = tk.Label(hero, text="\u542f\u52a8\u540e\u53ef\u4ee5\u7528\u5feb\u6377\u952e\uff0c\u4e5f\u53ef\u4ee5\u76f4\u63a5\u70b9\u6309\u94ae\u5f55\u97f3\u3002", fg=MUTED, bg=SURFACE, font=(FONT_UI, 14))
        self.hero_copy.pack(anchor="w", pady=(8, 0))

        actions = tk.Frame(hero, bg=SURFACE)
        actions.pack(anchor="w", pady=(20, 0))
        self.start_button = self.button(actions, "\u542f\u52a8\u8bed\u97f3\u5f15\u64ce", self.start_engine, primary=True)
        self.start_button.pack(side="left")
        self.mic_button = self.button(actions, "\u9ea6\u514b\u98ce\u5f55\u97f3 / \u505c\u6b62", lambda: self.safe_core_call(lambda: self.app.toggle_recording("microphone")))
        self.mic_button.pack(side="left", padx=(10, 0))
        self.system_button = self.button(actions, "\u7cfb\u7edf\u97f3\u9891 / \u505c\u6b62", lambda: self.safe_core_call(lambda: self.app.toggle_recording("system")))
        self.system_button.pack(side="left", padx=(10, 0))
        self.command_buttons.extend([self.mic_button, self.system_button])

        tools = tk.Frame(hero, bg=SURFACE)
        tools.pack(anchor="w", pady=(10, 0))
        self.reload_button = self.button(tools, "\u91cd\u8f7d\u70ed\u8bcd", lambda: self.safe_core_call(self.app.reload_phrases))
        self.reload_button.pack(side="left")
        self.open_button = self.button(tools, "\u6253\u5f00\u70ed\u8bcd\u6587\u4ef6", lambda: self.safe_core_call(self.app.open_phrases_file))
        self.open_button.pack(side="left", padx=(10, 0))
        self.float_button = self.button(tools, "\u663e\u793a\u60ac\u6d6e\u7a97", lambda: self.float_window.set_state({"status": "recording"}))
        self.float_button.pack(side="left", padx=(10, 0))
        self.scan_button = self.button(tools, "\u626b\u63cf\u672c\u673a\u6a21\u578b", self.scan_models)
        self.scan_button.pack(side="left", padx=(10, 0))
        self.command_buttons.extend([self.reload_button, self.open_button])

        settings = tk.Frame(main, bg=BG)
        settings.pack(fill="x", pady=(18, 0))
        self.add_option(settings, "\u9ea6\u514b\u98ce\u589e\u5f3a", "\u8f93\u5165\u9650\u5e45 + \u8f93\u51fa AGC/\u538b\u7f29", "audio_processing_enabled", [("\u5173\u95ed", False), ("\u5f00\u542f", True)])
        self.add_option(settings, "FRCRN \u964d\u566a", "\u5608\u6742\u73af\u5883\u53ef\u5f00\uff0c\u9996\u6b21\u4f1a\u52a0\u8f7d\u6a21\u578b", "noise_suppression_enabled", [("\u5173\u95ed", False), ("\u5f00\u542f", True)])
        self.add_option(settings, "ASR \u8bbe\u5907", "GPU \u66f4\u5feb\uff0cCPU \u66f4\u517c\u5bb9", "asr_device_mode", [("CPU", "0"), ("GPU", "1")])
        self.add_option(settings, "ASR \u5f15\u64ce", "\u5207\u6362\u540e\u4e0b\u4e00\u6b21\u8bc6\u522b\u4f7f\u7528\u65b0\u6a21\u578b", "asr_engine_mode", [("SenseVoice", "0"), ("Qwen ASR 0.6B", "1"), ("Qwen ASR 1.7B", "2")])
        self.add_option(settings, "\u6587\u672c\u4f18\u5316", "\u8bc6\u522b\u540e\u518d\u7528\u672c\u5730 Qwen \u4fee\u6b63\u6587\u7a3f", "text_optimizer_default", [("\u5173\u95ed", "0"), ("Qwen 0.6B", "1"), ("Qwen 1.7B", "2")])

        log_panel = self.panel(main, padx=16, pady=14)
        log_panel.pack(fill="both", expand=True, pady=(18, 0))
        log_top = tk.Frame(log_panel, bg=SURFACE)
        log_top.pack(fill="x")
        tk.Label(log_top, text="\u8fd0\u884c\u65e5\u5fd7", fg=TEXT, bg=SURFACE, font=(FONT_UI, 15, "bold")).pack(side="left")
        self.button(log_top, "\u6e05\u7a7a", self.clear_log).pack(side="right")
        self.log_text = tk.Text(log_panel, height=10, bg=LOG_BG, fg=LOG_FG, insertbackground=LOG_FG, relief="flat", wrap="word", font=("Cascadia Mono", 12))
        self.log_text.pack(fill="both", expand=True, pady=(10, 0))
        self.append_log("[ui] SenseVoice IME desktop ready.\n")

    def panel(self, master, padx=16, pady=16):
        return tk.Frame(master, bg=SURFACE, padx=padx, pady=pady, highlightbackground=LINE, highlightthickness=1)

    def button(self, master, text, command, primary=False):
        return tk.Button(
            master,
            text=text,
            command=command,
            bg=TEXT if primary else SURFACE_2,
            fg="white" if primary else TEXT,
            activebackground=ACCENT if primary else LINE,
            activeforeground="white" if primary else TEXT,
            relief="flat",
            padx=16,
            pady=9,
            font=(FONT_UI, 12, "bold" if primary else "normal"),
        )

    def add_option(self, parent, title, subtitle, key, choices):
        row = tk.Frame(parent, bg=SURFACE_2, padx=14, pady=12, highlightbackground=LINE, highlightthickness=1)
        row.pack(fill="x", pady=(0, 10))
        copy = tk.Frame(row, bg=SURFACE_2)
        copy.pack(side="left", fill="x", expand=True)
        tk.Label(copy, text=title, fg=TEXT, bg=SURFACE_2, font=(FONT_UI, 13, "bold")).pack(anchor="w")
        tk.Label(copy, text=subtitle, fg=MUTED, bg=SURFACE_2, font=(FONT_UI, 11)).pack(anchor="w", pady=(4, 0))
        group = tk.Frame(row, bg=SURFACE, padx=4, pady=4, highlightbackground=LINE, highlightthickness=1)
        group.pack(side="right")
        buttons = []
        for label, value in choices:
            button = tk.Button(group, text=label, relief="flat", padx=14, pady=9, font=(FONT_UI, 11), command=lambda k=key, v=value: self.set_option(k, v))
            button.pack(side="left")
            buttons.append((button, value))
        self.controls[key] = buttons

    def update_hotkey_label(self):
        text = (
            f"\u9ea6\u514b\u98ce: {self.config.get('push_to_talk_hotkey', 'f8')}\n"
            f"\u7cfb\u7edf\u97f3\u9891: {self.config.get('system_audio_hotkey', 'f9')}\n"
            f"\u91cd\u8f7d\u70ed\u8bcd: {self.config.get('reload_phrases_hotkey', 'f6')}\n"
            f"\u6253\u5f00\u70ed\u8bcd: {self.config.get('open_phrases_hotkey', 'f7')}"
        )
        self.hotkey_label.configure(text=text)

    def refresh_config_ui(self):
        values = {
            "audio_processing_enabled": bool(self.config.get("audio_processing_enabled", True)),
            "noise_suppression_enabled": bool(self.config.get("noise_suppression_enabled", False)),
            "asr_device_mode": str(self.config.get("asr_device_mode", self.config.get("asr_device_default", "1"))),
            "asr_engine_mode": str(self.config.get("asr_engine_mode", self.config.get("asr_engine_default", "0"))),
            "text_optimizer_default": str(self.config.get("text_optimizer_default", "0")),
        }
        for key, buttons in self.controls.items():
            active_value = values.get(key)
            for button, value in buttons:
                active = value == active_value
                button.configure(bg=TEXT if active else SURFACE, fg="white" if active else MUTED)
        self.update_hotkey_label()
        self.draw_status_dot(ACCENT)

    def set_controls_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for button in self.command_buttons:
            button.configure(state=state)

    def set_option(self, key, value):
        try:
            if self.ready and self.app:
                result = self.app.apply_runtime_config({key: value})
                self.config.update(self.app.config)
                self.config.update(result.get("config", {}))
            else:
                self.apply_offline_update(key, value)
                core.save_config(self.config)
            self.refresh_config_ui()
            self.set_status("\u5f85\u547d\u4e2d", "\u8bbe\u7f6e\u5df2\u66f4\u65b0", ACCENT)
        except Exception as exc:
            messagebox.showwarning("\u6682\u65f6\u4e0d\u80fd\u5207\u6362", str(exc))
            self.append_log(f"[ui] switch failed: {exc}\n")

    def scan_models(self):
        self.append_log("[model-scan] scanning local model folders...\n")
        try:
            result = core.discover_models(self.config, persist=True, verbose=True)
            changed = result.get("changed", {})
            if changed:
                self.append_log(f"[model-scan] updated {len(changed)} path(s).\n")
            else:
                self.append_log("[model-scan] no path changes needed.\n")
            self.refresh_config_ui()
        except Exception as exc:
            self.append_log(f"[model-scan] failed: {exc}\n")
            messagebox.showwarning("SenseVoice IME", str(exc))

    def apply_offline_update(self, key, value):
        if key == "asr_device_mode":
            self.config["asr_device_default"] = str(value)
            self.config["asr_device_mode"] = str(value)
            self.config["device"] = "cuda:0" if str(value) == "1" else "cpu"
        elif key == "asr_engine_mode":
            self.config["asr_engine_default"] = str(value)
            self.config["asr_engine_mode"] = str(value)
        else:
            self.config[key] = value

    def start_engine(self):
        if self.app_thread and self.app_thread.is_alive():
            return
        self.disable_prompts()
        self.scan_models()
        self.start_button.configure(text="\u8bed\u97f3\u5f15\u64ce\u542f\u52a8\u4e2d...", state="disabled")
        self.set_status("\u542f\u52a8\u4e2d", "\u6b63\u5728\u52a0\u8f7d\u6a21\u578b\u548c\u70ed\u952e", WARNING)
        self.app_thread = threading.Thread(target=self.engine_worker, daemon=True)
        self.app_thread.start()

    def engine_worker(self):
        try:
            self.app = core.ImeApp(self.config)
            self.app.print_help()
            self.app.engine.load()
            self.app.text_optimizer.load()
            self.app.recorder.ensure_stream()
            try:
                keyboard = core.require_import("keyboard")
                push_to_talk = self.app.config.get("push_to_talk_hotkey", "ctrl+alt+windows+l")
                system_audio_hotkey = self.app.config.get("system_audio_hotkey", "ctrl+alt+windows+m")
                self.app.register_push_to_talk(keyboard, push_to_talk)
                self.app.register_system_audio_hotkey(keyboard, system_audio_hotkey)
                keyboard.add_hotkey(self.app.config.get("reload_phrases_hotkey", "ctrl+alt+r"), self.app.reload_phrases)
                keyboard.add_hotkey(self.app.config.get("open_phrases_hotkey", "ctrl+alt+p"), self.app.open_phrases_file)
            except Exception as exc:
                print(f"[hotkey] global hotkeys unavailable; use the buttons in this window. {exc}")
            threading.Thread(target=self.app.worker_loop, daemon=True).start()
            threading.Thread(target=self.listen_to_core_events, daemon=True).start()
            self.event_queue.put(("ready", {"status": "idle", "hint": "\u8bed\u97f3\u5f15\u64ce\u5df2\u542f\u52a8"}))
            while not self.closing:
                time.sleep(0.3)
        except Exception as exc:
            self.event_queue.put(("error", str(exc)))

    def listen_to_core_events(self):
        subscriber = self.app.state_bus.subscribe()
        while not self.closing:
            payload = subscriber.get()
            self.event_queue.put(("state", payload))

    def safe_core_call(self, func):
        if not self.ready or not self.app:
            messagebox.showinfo("SenseVoice IME", "\u8bf7\u5148\u542f\u52a8\u8bed\u97f3\u5f15\u64ce\u3002")
            return
        threading.Thread(target=self.run_core_call, args=(func,), daemon=True).start()

    def run_core_call(self, func):
        try:
            func()
        except Exception as exc:
            self.event_queue.put(("error", str(exc)))

    def drain_events(self):
        try:
            while True:
                kind, payload = self.event_queue.get_nowait()
                if kind == "log":
                    self.append_log(payload)
                elif kind == "state":
                    self.apply_state(payload)
                elif kind == "ready":
                    self.ready = True
                    self.apply_state(payload)
                    self.start_button.configure(text="\u8bed\u97f3\u5f15\u64ce\u8fd0\u884c\u4e2d", state="disabled")
                    self.set_controls_enabled(True)
                elif kind == "error":
                    self.ready = False
                    self.set_status("\u9519\u8bef", payload, DANGER)
                    self.start_button.configure(text="\u91cd\u65b0\u542f\u52a8\u8bed\u97f3\u5f15\u64ce", state="normal")
                    self.set_controls_enabled(False)
                    messagebox.showerror("SenseVoice IME", payload)
        except queue.Empty:
            pass
        self.root.after(120, self.drain_events)

    def apply_state(self, payload):
        status = payload.get("status", "idle")
        hint = payload.get("hint", "")
        if status == "recording":
            self.set_status("\u5f55\u97f3\u4e2d", hint or T["voice_input"], DANGER)
            self.hero_title.configure(text="\u6b63\u5728\u8046\u542c")
            self.hero_copy.configure(text="\u518d\u6b21\u6309\u5feb\u6377\u952e\u6216\u70b9\u5f55\u97f3\u6309\u94ae\u505c\u6b62\uff0c\u7136\u540e\u5f00\u59cb\u8bc6\u522b\u3002")
        elif status == "processing":
            self.set_status("\u8bc6\u522b\u4e2d", hint or "\u6b63\u5728\u8f6c\u5199\u6587\u672c", WARNING)
            self.hero_title.configure(text="\u6b63\u5728\u8bc6\u522b")
            self.hero_copy.configure(text="SenseVoice \u6b63\u5728\u8f6c\u5199\uff0c\u5fc5\u8981\u65f6\u4f1a\u4ea4\u7ed9 Qwen \u4f18\u5316\u3002")
        elif status == "done":
            self.set_status("\u5df2\u5b8c\u6210", hint or T["text_output"], ACCENT)
            self.hero_title.configure(text="\u5df2\u5b8c\u6210")
            self.hero_copy.configure(text=payload.get("text", "\u8bc6\u522b\u7ed3\u679c\u5df2\u7ecf\u751f\u6210\u3002"))
        else:
            self.set_status("\u5f85\u547d\u4e2d", hint or "\u6309\u5feb\u6377\u952e\u6216\u70b9\u6309\u94ae\u5f00\u59cb\u5f55\u97f3", ACCENT)
            self.hero_title.configure(text=T["ready"])
            self.hero_copy.configure(text="\u628a\u5149\u6807\u653e\u5230\u8f93\u5165\u6846\uff0c\u7528\u5feb\u6377\u952e\u6216\u6309\u94ae\u5f00\u59cb\u5f55\u97f3\u3002")
        self.float_window.set_state(payload)

    def append_log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def set_status(self, title, hint, color):
        self.status_text.configure(text=f"{title}\n{hint}")
        self.draw_status_dot(color)

    def draw_status_dot(self, color):
        self.status_dot.delete("all")
        self.status_dot.create_oval(4, 4, 14, 14, fill=color, outline="")

    def on_close(self):
        self.closing = True
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        self.root.destroy()
        os._exit(0)

    def run(self):
        self.root.mainloop()


def main():
    if not ensure_single_instance():
        return
    DesktopApp().run()


if __name__ == "__main__":
    main()
