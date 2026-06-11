import argparse
from collections import deque
from datetime import datetime
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
RAW_TRANSCRIPTS_PATH = Path(__file__).with_name("raw_transcripts.jsonl")


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
    phrases.sort(key=lambda item: len(item[0]), reverse=True)
    return phrases


def phrase_pattern(spoken):
    escaped = re.escape(spoken)
    if re.match(r"^[A-Za-z0-9]", spoken) or re.search(r"[A-Za-z0-9]$", spoken):
        return rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    return escaped


def apply_phrases(text, phrases):
    result = text
    for spoken, replacement in phrases:
        result = re.sub(phrase_pattern(spoken), replacement, result, flags=re.IGNORECASE)
    return result


DISALLOWED_SCRIPT_RE = re.compile(r"[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF\u3040-\u30FF\uFF66-\uFF9D]+")


def sanitize_output_language(text, config):
    if not bool(config.get("restrict_output_to_zh_en", True)):
        return text
    result = DISALLOWED_SCRIPT_RE.sub(" ", str(text or ""))
    result = re.sub(r"\s+", " ", result).strip()
    result = re.sub(r"\s+([，。！？、,.!?;:；：])", r"\1", result)
    result = re.sub(r"([（(])\s+", r"\1", result)
    result = re.sub(r"\s+([）)])", r"\1", result)
    return result



def resolve_project_path(config_value, default_path):
    raw_path = str(config_value or default_path).strip()
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = CONFIG_PATH.parent / path
    return path


def append_raw_transcript_log(config, entry):
    if not bool(config.get("log_raw_transcripts", True)):
        return
    log_path = resolve_project_path(config.get("raw_transcripts_path"), RAW_TRANSCRIPTS_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")



def _play_builtin_beep(freq=880, duration=0.08, volume=0.25):
    try:
        import sounddevice as sd
        sample_rate = 16000
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        wave = volume * np.sin(2 * np.pi * freq * t)
        sd.play(wave, samplerate=sample_rate, blocking=False)
    except Exception:
        pass


def play_sound(config_value, default_freq=880, default_duration=0.08):
    """Play a sound cue.

    config_value can be:
      - True  -> play the built-in beep
      - False -> silent
      - str   -> path to a WAV file to play
    """
    if config_value is False:
        return
    if isinstance(config_value, str) and config_value.strip():
        wav_path = Path(config_value.strip())
        if not wav_path.is_absolute():
            wav_path = CONFIG_PATH.parent / wav_path
        try:
            import sounddevice as sd
            import soundfile as sf
            data, fs = sf.read(str(wav_path))
            sd.play(data, samplerate=fs, blocking=False)
        except Exception:
            pass
        return
    # Default: built-in beep
    _play_builtin_beep(freq=default_freq, duration=default_duration)


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


class TextOptimizer:
    MODES = {
        "0": {"name": "off", "config_key": None},
        "1": {"name": "Qwen3-0.6B", "config_key": "qwen_0_6b_path"},
        "2": {"name": "Qwen3-1.7B", "config_key": "qwen_1_7b_path"},
    }

    def __init__(self, config, mode="0"):
        self.config = config
        self.mode = str(mode or "0").strip()
        if self.mode not in self.MODES:
            self.mode = "0"
        self.tokenizer = None
        self.model = None
        self.device = None

    @property
    def enabled(self):
        return self.mode != "0"

    @property
    def name(self):
        return self.MODES[self.mode]["name"]

    def model_path(self):
        config_key = self.MODES[self.mode]["config_key"]
        raw_path = self.config.get(config_key, "") if config_key else ""
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = CONFIG_PATH.parent / path
        return path

    def load(self):
        if not self.enabled or self.model is not None:
            return
        model_path = self.model_path()
        if not model_path.exists():
            raise FileNotFoundError(f"Text optimizer model path does not exist: {model_path}")
        if not (model_path / "config.json").exists():
            raise FileNotFoundError(
                f"Text optimizer model looks incomplete, missing config.json: {model_path}"
            )

        torch = require_import("torch")
        transformers = require_import("transformers", "transformers")
        AutoTokenizer = transformers.AutoTokenizer
        AutoModelForCausalLM = transformers.AutoModelForCausalLM

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = "auto"
        print(f"[optimizer] loading {self.name} from {model_path}")
        print(f"[optimizer] device: {self.device}")
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(model_path),
            local_files_only=True,
            trust_remote_code=True,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_path),
            torch_dtype=dtype,
            local_files_only=True,
            trust_remote_code=True,
        )
        self.model.to(self.device)
        self.model.eval()
        print("[optimizer] ready")

    def unload(self):
        if self.model is None and self.tokenizer is None:
            return
        print(f"[optimizer] unloading {self.name}")
        self.model = None
        self.tokenizer = None
        try:
            import gc
            gc.collect()
            torch = require_import("torch")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def build_prompt(self, text):
        system = (
            "你是中文语音输入法后处理器。只修正语音识别错误、错别字、"
            "同音词、标点和断句。不要扩写，不要解释，不要改变用户语气。"
        )
        user = f"识别文本：{text}\n\n只输出修正后的文本。"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if hasattr(self.tokenizer, "apply_chat_template"):
            try:
                return self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
            except TypeError:
                return self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
        return f"{system}\n\n{user}\n"

    def cleanup_output(self, output):
        output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL | re.IGNORECASE).strip()
        if "</think>" in output:
            output = output.split("</think>", 1)[-1].strip()
        return output.strip().strip('"').strip("'")

    def optimize(self, text):
        text = str(text or "").strip()
        if not self.enabled or not text:
            return text
        self.load()
        torch = require_import("torch")
        prompt = self.build_prompt(text)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        max_new_tokens = int(self.config.get("text_optimizer_max_new_tokens", 128))
        with torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        new_tokens = output_ids[0][inputs["input_ids"].shape[-1]:]
        optimized = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        optimized = self.cleanup_output(optimized)
        return optimized or text


def choose_text_optimizer_mode(config, current_mode=None):
    default_mode = str(current_mode or config.get("text_optimizer_default", "0")).strip()
    if default_mode not in TextOptimizer.MODES:
        default_mode = "0"
    if current_mode is None and not bool(config.get("prompt_text_optimizer_on_start", True)):
        return default_mode
    print("Text optimizer:")
    print("  0 = off / keep current behavior")
    print("  1 = Qwen3-0.6B")
    print("  2 = Qwen3-1.7B")
    try:
        choice = input(f"Choose text optimizer [0/1/2, default {default_mode}]: ").strip()
    except EOFError:
        choice = ""
    return choice if choice in TextOptimizer.MODES else default_mode


class Recorder:
    def __init__(self, config):
        self.sd = require_import("sounddevice")
        self.sf = require_import("soundfile")
        self.config = config
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.channels = int(config.get("channels", 1))
        self.pre_roll_seconds = float(config.get("pre_roll_seconds", 0.5))
        self.pre_roll_samples = max(0, int(self.sample_rate * self.pre_roll_seconds))
        self.pre_frames = deque()
        self.pre_frame_samples = 0
        self.frames = []
        self.stream = None
        self.recording = False
        self.started_at = None
        self.lock = threading.Lock()

    @property
    def is_recording(self):
        return self.recording

    def ensure_stream(self):
        with self.lock:
            if self.stream is not None:
                return
            self.stream = self.sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._callback,
            )
            self.stream.start()
            print(f"[audio] stream ready, pre-roll={self.pre_roll_seconds:.2f}s")

    def start(self):
        self.ensure_stream()
        with self.lock:
            if self.recording:
                return False
            self.frames = [frame.copy() for frame in self.pre_frames]
            self.started_at = time.time()
            self.recording = True
            return True

    def _trim_pre_roll_locked(self):
        while self.pre_frame_samples > self.pre_roll_samples and self.pre_frames:
            old = self.pre_frames.popleft()
            self.pre_frame_samples -= old.shape[0]

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"[audio] {status}")
        chunk = indata.copy()
        with self.lock:
            if self.pre_roll_samples > 0:
                self.pre_frames.append(chunk)
                self.pre_frame_samples += chunk.shape[0]
                self._trim_pre_roll_locked()
            if self.recording:
                self.frames.append(chunk)

    def stop_to_wav(self):
        with self.lock:
            if not self.recording:
                return None, 0.0, 0.0
            self.recording = False
            duration = time.time() - (self.started_at or time.time())
            frames = [frame.copy() for frame in self.frames]
            self.frames = []
        if not frames:
            return None, duration, 0.0
        audio = np.concatenate(frames, axis=0)
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
        self.optimizer_lock = threading.RLock()
        self.text_optimizer = TextOptimizer(config, choose_text_optimizer_mode(config))
        self.recorder = Recorder(config)
        self.jobs = queue.Queue()
        self.busy = False
        self.normalized_push_to_talk = None

    def print_help(self):
        print("SenseVoice IME MVP")
        print(f"  Hold to record   : {self.config.get('push_to_talk_hotkey', '`')}")
        print(f"  Reload phrases   : {self.config.get('reload_phrases_hotkey', 'ctrl+alt+r')}")
        print(f"  Open phrases     : {self.config.get('open_phrases_hotkey', 'ctrl+alt+p')}")
        print("  Rechoose model   : type qqq + Enter in this terminal")
        print("  Quit             : esc")
        print(f"  Text optimizer   : {self.text_optimizer.name}")
        print(f"  Phrases file     : {PHRASES_PATH}")
        print(f"  Raw ASR log      : {resolve_project_path(self.config.get('raw_transcripts_path'), RAW_TRANSCRIPTS_PATH)}")
        print("")

    def start(self):
        keyboard = require_import("keyboard")
        self.print_help()
        self.engine.load()
        self.text_optimizer.load()
        self.recorder.ensure_stream()
        push_to_talk = self.config.get("push_to_talk_hotkey", "`")
        self.register_push_to_talk(keyboard, push_to_talk)
        keyboard.add_hotkey(self.config.get("reload_phrases_hotkey", "ctrl+alt+r"), self.reload_phrases)
        keyboard.add_hotkey(self.config.get("open_phrases_hotkey", "ctrl+alt+p"), self.open_phrases_file)
        worker = threading.Thread(target=self.worker_loop, daemon=True)
        worker.start()
        command_listener = threading.Thread(target=self.command_loop, daemon=True)
        command_listener.start()
        print("[ready] Put your cursor in any text box, hold the push-to-talk hotkey, speak, then release it.")
        keyboard.wait("esc")
        print("[quit]")

    def register_push_to_talk(self, keyboard, hotkey):
        normalized = normalize_hotkey_for_keyboard(hotkey)
        self.normalized_push_to_talk = normalized
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
            lambda: self.stop_recording_if_needed(force=False),
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
            start_sound = self.config.get("sound_on_start", True)
            if start_sound is not False:
                play_sound(start_sound, default_freq=880, default_duration=0.08)
            print("[recording] started")
            max_seconds = float(self.config.get("max_record_seconds", 60))
            threading.Timer(max_seconds, lambda: self.stop_recording_if_needed(force=True)).start()

    def stop_recording_if_needed(self, force=False):
        if not self.recorder.is_recording:
            return
        if not force:
            debounce_seconds = float(self.config.get("hotkey_release_debounce_seconds", 0.12))
            if debounce_seconds > 0:
                time.sleep(debounce_seconds)
            try:
                keyboard = require_import("keyboard")
                if self.normalized_push_to_talk and keyboard.is_pressed(self.normalized_push_to_talk):
                    print("[hotkey] ignored release bounce")
                    return
            except Exception:
                pass
        stop_sound = self.config.get("sound_on_stop", True)
        if stop_sound is not False:
            play_sound(stop_sound, default_freq=440, default_duration=0.12)
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
        self.jobs.put((wav_path, duration, rms))

    def worker_loop(self):
        while True:
            wav_path, duration, rms = self.jobs.get()
            self.busy = True
            try:
                print("[transcribe] working...")
                asr_text = self.engine.transcribe(wav_path)
                asr_for_phrases = sanitize_output_language(asr_text, self.config)
                asr_after_phrases = apply_phrases(asr_for_phrases, self.phrases)
                with self.optimizer_lock:
                    optimizer_mode = self.text_optimizer.mode
                    optimizer_name = self.text_optimizer.name
                    text = self.text_optimizer.optimize(asr_after_phrases)
                text = sanitize_output_language(text, self.config)
                append_raw_transcript_log(self.config, {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "duration_seconds": round(float(duration), 3),
                    "rms": round(float(rms), 6),
                    "optimizer_mode": optimizer_mode,
                    "optimizer_name": optimizer_name,
                    "asr_raw": asr_text,
                    "asr_sanitized": asr_for_phrases,
                    "asr_after_phrases": asr_after_phrases,
                    "final_text": text,
                })
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

    def command_loop(self):
        print("[command] Type qqq then Enter to rechoose the text optimizer model.")
        while True:
            try:
                line = sys.stdin.readline()
            except Exception:
                return
            if not line:
                return
            command = line.strip().lower()
            if command == "qqq":
                self.rechoose_text_optimizer()
            elif command:
                print(f"[command] unknown command: {command}")

    def rechoose_text_optimizer(self):
        current_mode = self.text_optimizer.mode
        new_mode = choose_text_optimizer_mode(self.config, current_mode=current_mode)
        if new_mode == current_mode:
            print(f"[optimizer] unchanged: {self.text_optimizer.name}")
            return
        new_optimizer = TextOptimizer(self.config, new_mode)
        with self.optimizer_lock:
            self.text_optimizer.unload()
            self.text_optimizer = new_optimizer
            try:
                self.text_optimizer.load()
            except Exception as exc:
                print(f"[optimizer] failed to switch: {exc}")
                self.text_optimizer = TextOptimizer(self.config, "0")
                print("[optimizer] switched to off")
                return
        print(f"[optimizer] switched to {self.text_optimizer.name}")

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
    app.recorder.ensure_stream()
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
    asr_text = app.engine.transcribe(wav_path)
    asr_for_phrases = sanitize_output_language(asr_text, config)
    asr_after_phrases = apply_phrases(asr_for_phrases, app.phrases)
    with app.optimizer_lock:
        optimizer_mode = app.text_optimizer.mode
        optimizer_name = app.text_optimizer.name
        text = app.text_optimizer.optimize(asr_after_phrases)
    text = sanitize_output_language(text, config)
    append_raw_transcript_log(config, {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "duration_seconds": round(float(duration), 3),
        "rms": round(float(rms), 6),
        "optimizer_mode": optimizer_mode,
        "optimizer_name": optimizer_name,
        "asr_raw": asr_text,
        "asr_sanitized": asr_for_phrases,
        "asr_after_phrases": asr_after_phrases,
        "final_text": text,
    })
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

