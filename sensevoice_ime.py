import argparse
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

CONFIG_PATH = Path(__file__).with_name("config.json")
PHRASES_PATH = Path(__file__).with_name("phrases.json")


class MissingDependency(RuntimeError):
    pass


def require_import(name, package_hint=None):
    try:
        return __import__(name)
    except ImportError as exc:
        hint = package_hint or name
        raise MissingDependency(f"Missing dependency: {name}. Install it with: python -m pip install {hint}") from exc


def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_config():
    return load_json(CONFIG_PATH, {})


def load_phrases():
    data = load_json(PHRASES_PATH, [])
    phrases = []
    for item in data:
        spoken = str(item.get("spoken", "")).strip()
        replacement = str(item.get("replace", "")).strip()
        if spoken and replacement:
            phrases.append((spoken, replacement))
    return phrases


def apply_phrases(text, phrases):
    result = text
    for spoken, replacement in phrases:
        result = re.sub(re.escape(spoken), replacement, result, flags=re.IGNORECASE)
    return result



def normalize_hotkey_for_keyboard(hotkey):
    # The keyboard package names the backtick key "grave" on Windows.
    return str(hotkey).replace("`", "grave")


def choose_device(config):
    device = str(config.get("device", "auto")).strip().lower()
    if device and device != "auto":
        return device
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass
    return "cpu"


class SenseVoiceEngine:
    def __init__(self, config):
        self.config = config
        self.model = None
        self.device = choose_device(config)

    def load(self):
        if self.model is not None:
            return
        model_path = Path(self.config.get("model_path", "")).expanduser()
        if not model_path.exists():
            raise FileNotFoundError(f"Model path does not exist: {model_path}")
        from funasr import AutoModel
        print(f"[model] loading SenseVoice from {model_path}")
        print(f"[model] device: {self.device}")
        self.model = AutoModel(
            model=str(model_path),
            trust_remote_code=False,
            device=self.device,
            disable_update=True,
        )
        print("[model] ready")

    def transcribe(self, wav_path):
        self.load()
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        res = self.model.generate(
            input=str(wav_path),
            cache={},
            language=self.config.get("language", "auto"),
            use_itn=True,
            batch_size_s=60,
        )
        if not res:
            return ""
        return rich_transcription_postprocess(res[0].get("text", "")).strip()


class Recorder:
    def __init__(self, config):
        self.sd = require_import("sounddevice")
        self.sf = require_import("soundfile")
        self.config = config
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.channels = int(config.get("channels", 1))
        self.frames = []
        self.stream = None
        self.started_at = None
        self.lock = threading.Lock()

    @property
    def is_recording(self):
        return self.stream is not None

    def start(self):
        with self.lock:
            if self.stream is not None:
                return False
            self.frames = []
            self.started_at = time.time()
            self.stream = self.sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._callback,
            )
            self.stream.start()
            return True

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"[audio] {status}")
        self.frames.append(indata.copy())

    def stop_to_wav(self):
        with self.lock:
            if self.stream is None:
                return None, 0.0
            stream = self.stream
            self.stream = None
        stream.stop()
        stream.close()
        duration = time.time() - (self.started_at or time.time())
        if not self.frames:
            return None, duration, 0.0
        audio = np.concatenate(self.frames, axis=0)
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        fd, name = tempfile.mkstemp(prefix="sensevoice_ime_", suffix=".wav")
        os.close(fd)
        self.sf.write(name, audio, self.sample_rate)
        return Path(name), duration, rms


def paste_text(text, restore_clipboard=False):
    pyperclip = require_import("pyperclip")
    keyboard = require_import("keyboard")
    old_clipboard = None
    if restore_clipboard:
        try:
            old_clipboard = pyperclip.paste()
        except Exception:
            old_clipboard = None
    pyperclip.copy(text)
    time.sleep(0.08)
    keyboard.send("ctrl+v")
    if restore_clipboard and old_clipboard is not None:
        time.sleep(0.5)
        pyperclip.copy(old_clipboard)


class ImeApp:
    def __init__(self, config):
        self.config = config
        self.phrases = load_phrases()
        self.engine = SenseVoiceEngine(config)
        self.recorder = Recorder(config)
        self.jobs = queue.Queue()
        self.busy = False

    def print_help(self):
        print("SenseVoice IME MVP")
        print(f"  Hold to record   : {self.config.get('push_to_talk_hotkey', 'ctrl+`')}")
        print(f"  Reload phrases   : {self.config.get('reload_phrases_hotkey', 'ctrl+alt+r')}")
        print(f"  Open phrases     : {self.config.get('open_phrases_hotkey', 'ctrl+alt+p')}")
        print("  Quit             : esc")
        print(f"  Phrases file     : {PHRASES_PATH}")
        print("")

    def start(self):
        keyboard = require_import("keyboard")
        self.print_help()
        self.engine.load()
        push_to_talk = self.config.get("push_to_talk_hotkey", "ctrl+`")
        self.register_push_to_talk(keyboard, push_to_talk)
        keyboard.add_hotkey(self.config.get("reload_phrases_hotkey", "ctrl+alt+r"), self.reload_phrases)
        keyboard.add_hotkey(self.config.get("open_phrases_hotkey", "ctrl+alt+p"), self.open_phrases_file)
        worker = threading.Thread(target=self.worker_loop, daemon=True)
        worker.start()
        print("[ready] Put your cursor in any text box, hold the push-to-talk hotkey, speak, then release it.")
        keyboard.wait("esc")
        print("[quit]")

    def register_push_to_talk(self, keyboard, hotkey):
        normalized = normalize_hotkey_for_keyboard(hotkey)
        # Register with suppress=True so the combo is intercepted before
        # focused applications (e.g. VS Code / Codex) can handle it.
        keyboard.add_hotkey(
            normalized,
            self.start_recording,
            suppress=True,
            trigger_on_release=False,
        )
        keyboard.add_hotkey(
            normalized,
            self.stop_recording_if_needed,
            suppress=True,
            trigger_on_release=True,
        )
        print(f"[hotkey] registered push-to-talk as {normalized} (suppressed)")

    def start_recording(self):
        if self.busy:
            print("[busy] transcription is still running")
            return
        if self.recorder.is_recording:
            return
        if self.recorder.start():
            print("[recording] started")
            max_seconds = float(self.config.get("max_record_seconds", 60))
            threading.Timer(max_seconds, self.stop_recording_if_needed).start()

    def stop_recording_if_needed(self):
        if not self.recorder.is_recording:
            return
        wav_path, duration, rms = self.recorder.stop_to_wav()
        print(f"[recording] stopped after {duration:.1f}s, rms={rms:.4f}")
        min_seconds = float(self.config.get("min_record_seconds", 0.3))
        if not wav_path or duration < min_seconds:
            print("[skip] recording too short")
            return
        min_rms = float(self.config.get("min_rms", 0.0))
        if rms < min_rms:
            print(f"[skip] audio too quiet, rms {rms:.4f} < {min_rms:.4f}")
            Path(wav_path).unlink(missing_ok=True)
            return
        self.jobs.put(wav_path)

    def worker_loop(self):
        while True:
            wav_path = self.jobs.get()
            self.busy = True
            try:
                print("[transcribe] working...")
                text = self.engine.transcribe(wav_path)
                text = apply_phrases(text, self.phrases)
                if self.config.get("append_space", False) and text:
                    text += " "
                print(f"[text] {text}")
                if text and self.config.get("paste_after_transcribe", True):
                    paste_text(text, bool(self.config.get("restore_clipboard", False)))
                    print("[paste] sent to active input")
            except Exception as exc:
                print(f"[error] {exc}")
            finally:
                try:
                    Path(wav_path).unlink(missing_ok=True)
                except Exception:
                    pass
                self.busy = False
                self.jobs.task_done()

    def reload_phrases(self):
        self.phrases = load_phrases()
        print(f"[phrases] loaded {len(self.phrases)} item(s)")

    def open_phrases_file(self):
        if not PHRASES_PATH.exists():
            PHRASES_PATH.write_text("[]\n", encoding="utf-8")
        os.startfile(str(PHRASES_PATH))
        print(f"[phrases] opened {PHRASES_PATH}")


def list_devices():
    sd = require_import("sounddevice")
    print(sd.query_devices())


def test_model(config):
    model_path = Path(config.get("model_path", ""))
    wav = model_path / "example" / "zh.mp3"
    engine = SenseVoiceEngine(config)
    text = engine.transcribe(wav)
    text = apply_phrases(text, load_phrases())
    print(f"[test] {text}")


def record_once(config, seconds, paste):
    app = ImeApp(config)
    app.engine.load()
    print(f"[recording] fixed {seconds}s")
    app.recorder.start()
    time.sleep(seconds)
    wav_path, duration, rms = app.recorder.stop_to_wav()
    print(f"[recording] stopped after {duration:.1f}s, rms={rms:.4f}")
    min_rms = float(config.get("min_rms", 0.0))
    if rms < min_rms:
        print(f"[skip] audio too quiet, rms {rms:.4f} < {min_rms:.4f}")
        Path(wav_path).unlink(missing_ok=True)
        return
    text = app.engine.transcribe(wav_path)
    text = apply_phrases(text, app.phrases)
    print(f"[text] {text}")
    if paste and text:
        paste_text(text, bool(config.get("restore_clipboard", False)))
        print("[paste] sent to active input")
    Path(wav_path).unlink(missing_ok=True)


def main():
    global CONFIG_PATH
    parser = argparse.ArgumentParser(description="Minimal SenseVoice push-to-talk dictation IME for Windows.")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to config.json")
    parser.add_argument("--list-devices", action="store_true", help="Print audio devices and exit")
    parser.add_argument("--test-model", action="store_true", help="Run SenseVoice on bundled zh.mp3")
    parser.add_argument("--once", type=float, default=0, help="Record a fixed number of seconds, transcribe, then exit")
    parser.add_argument("--no-paste", action="store_true", help="Do not paste result into the active input")
    args = parser.parse_args()

    CONFIG_PATH = Path(args.config)
    config = load_config()

    try:
        if args.list_devices:
            list_devices()
        elif args.test_model:
            test_model(config)
        elif args.once > 0:
            record_once(config, args.once, not args.no_paste)
        else:
            ImeApp(config).start()
    except MissingDependency as exc:
        print(f"[dependency] {exc}")
        return 2
    except KeyboardInterrupt:
        print("[quit]")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
