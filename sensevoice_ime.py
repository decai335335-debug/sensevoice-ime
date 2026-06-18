import argparse
from collections import deque
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import numpy as np

from tools.audio_processor import InputGuard, OutputPolish, choose_audio_processing_mode, audio_rms
from tools.noise_suppressor import NoiseSuppressor, choose_noise_suppression_mode

CONFIG_PATH = Path(__file__).with_name("config.json")
PHRASES_PATH = Path(__file__).with_name("phrases.json")
RAW_TRANSCRIPTS_PATH = Path(__file__).with_name("raw_transcripts.jsonl")
FRONTEND_PATH = Path(__file__).resolve().parent.parent / "sensevoice_ime_frontend"


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
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_config():
    return load_json(CONFIG_PATH, {})


def save_config(config):
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


MODEL_DEFINITIONS = {
    "model_path": {
        "label": "SenseVoiceSmall",
        "names": ["SenseVoiceSmall"],
        "required": ["configuration.json", "config.yaml", "am.mvn"],
    },
    "qwen_0_6b_path": {
        "label": "Qwen3-0.6B",
        "names": ["Qwen3-0.6B", "Qwen3-0___6B", "Qwen3-0_6B", "千问3-0.6B", "鍗冮棶3-0.6B"],
        "required": ["config.json"],
    },
    "qwen_1_7b_path": {
        "label": "Qwen3-1.7B",
        "names": ["Qwen3-1.7B", "Qwen3-1___7B", "Qwen3-1_7B", "千问3-1.7B", "鍗冮棶3-1.7B"],
        "required": ["config.json"],
    },
    "qwen_asr_0_6b_path": {
        "label": "Qwen3-ASR-0.6B",
        "names": ["Qwen3-ASR-0.6B", "Qwen3-ASR-0___6B", "Qwen3-ASR-0_6B"],
        "required": ["config.json"],
    },
    "qwen_asr_1_7b_path": {
        "label": "Qwen3-ASR-1.7B",
        "names": ["Qwen3-ASR-1.7B", "Qwen3-ASR-1___7B", "Qwen3-ASR-1_7B"],
        "required": ["config.json"],
    },
    "noise_suppression_model_path": {
        "label": "FRCRN noise suppression",
        "names": ["FRCRN语音降噪-单麦-16k", "FRCRN", "speech_frcrn_ans_cirm_16k"],
        "required": [],
    },
}


def model_search_roots():
    roots = [
        CONFIG_PATH.parent / "model",
        CONFIG_PATH.parent.parent / "model",
        Path.cwd() / "model",
        Path.home() / ".cache" / "modelscope" / "hub" / "models",
        Path.home() / ".cache" / "huggingface" / "hub",
    ]
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        drive_root = Path(f"{drive}:\\")
        if drive_root.exists():
            roots.extend([
                drive_root / "model",
                drive_root / "models",
                drive_root / "AI" / "models",
                drive_root / "Projects" / "ai",
            ])
    unique = []
    seen = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except Exception:
            resolved = root
        key = str(resolved).lower()
        if key not in seen and root.exists():
            seen.add(key)
            unique.append(root)
    return unique


def model_dir_matches(path, definition):
    if not path.is_dir():
        return False
    name = path.name.lower()
    expected_names = [item.lower() for item in definition["names"]]
    if not any(expected in name for expected in expected_names):
        return False
    required = definition.get("required", [])
    return not required or any((path / marker).exists() for marker in required)


def find_model_dir(definition, max_depth=5):
    for root in model_search_roots():
        stack = [(root, 0)]
        while stack:
            current, depth = stack.pop()
            if model_dir_matches(current, definition):
                return current
            if depth >= max_depth:
                continue
            try:
                children = [child for child in current.iterdir() if child.is_dir()]
            except Exception:
                continue
            stack.extend((child, depth + 1) for child in children)
    return None


def discover_models(config, persist=False, verbose=True):
    found = {}
    changed = {}
    for key, definition in MODEL_DEFINITIONS.items():
        configured = resolve_project_path(config.get(key), CONFIG_PATH.parent / "model")
        if configured.exists():
            found[key] = str(configured)
            continue
        discovered = find_model_dir(definition)
        if discovered:
            config[key] = str(discovered)
            found[key] = str(discovered)
            changed[key] = str(discovered)
            if verbose:
                print(f"[model-scan] {definition['label']}: {discovered}")
        elif verbose:
            print(f"[model-scan] {definition['label']}: not found")
    if changed and persist:
        save_config(config)
    return {"found": found, "changed": changed}


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


def torch_cuda_available():
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def choose_device(config):
    device = str(config.get("device", "auto")).strip().lower()
    if device and device != "auto":
        return device
    if torch_cuda_available():
        return "cuda:0"
    return "cpu"


def choose_asr_device_mode(config):
    modes = {"0": "cpu", "1": "gpu"}
    default_mode = str(config.get("asr_device_default", "1")).strip()
    if default_mode not in modes:
        default_mode = "1"
    if bool(config.get("prompt_asr_device_on_start", True)):
        print("ASR device:")
        print("  0 = CPU / compatible but slower")
        print("  1 = GPU / CUDA, fastest if CUDA PyTorch is installed")
        try:
            choice = input(f"Choose ASR device [0/1, default {default_mode}]: ").strip()
        except EOFError:
            choice = ""
        mode = choice if choice in modes else default_mode
    else:
        mode = default_mode
    config["asr_device_mode"] = mode
    config["device"] = "cuda:0" if mode == "1" else "cpu"
    return choose_device(config)


def choose_asr_engine_mode(config):
    modes = {"0": "SenseVoiceSmall", "1": "Qwen3-ASR-0.6B", "2": "Qwen3-ASR-1.7B"}
    default_mode = str(config.get("asr_engine_default", "0")).strip()
    if default_mode not in modes:
        default_mode = "0"
    if not bool(config.get("prompt_asr_engine_on_start", True)):
        return default_mode
    print("ASR engine:")
    print("  0 = SenseVoiceSmall / current default")
    print("  1 = Qwen3-ASR-0.6B")
    print("  2 = Qwen3-ASR-1.7B")
    try:
        choice = input(f"Choose ASR engine [0/1/2, default {default_mode}]: ").strip()
    except EOFError:
        choice = ""
    return choice if choice in modes else default_mode


class SenseVoiceEngine:
    name = "SenseVoiceSmall"

    def __init__(self, config):
        self.config = config
        self.model = None
        self.device = choose_device(config)

    def load(self):
        if self.model is not None:
            return
        model_path = Path(self.config.get("model_path", "")).expanduser()
        if not model_path.exists():
            discover_models(self.config, persist=True)
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


class QwenAsrEngine:
    MODES = {
        "1": {"name": "Qwen3-ASR-0.6B", "config_key": "qwen_asr_0_6b_path"},
        "2": {"name": "Qwen3-ASR-1.7B", "config_key": "qwen_asr_1_7b_path"},
    }

    def __init__(self, config, mode):
        self.config = config
        self.mode = str(mode)
        self.info = self.MODES[self.mode]
        self.model = None
        self.device = choose_device(config)

    @property
    def name(self):
        return self.info["name"]

    def model_path(self):
        raw_path = str(self.config.get(self.info["config_key"], "")).strip()
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = CONFIG_PATH.parent / path
        return path

    def load(self):
        if self.model is not None:
            return
        model_path = self.model_path()
        if not model_path.exists():
            discover_models(self.config, persist=True)
            model_path = self.model_path()
        if not model_path.exists():
            raise FileNotFoundError(f"Qwen ASR model path does not exist: {model_path}")
        if not (model_path / "config.json").exists():
            raise FileNotFoundError(f"Qwen ASR model looks incomplete, missing config.json: {model_path}")
        torch = require_import("torch")
        from qwen_asr import Qwen3ASRModel
        dtype = torch.bfloat16 if str(self.device).startswith("cuda") else torch.float32
        device_map = self.device if str(self.device).startswith("cuda") else "cpu"
        print(f"[model] loading {self.name} from {model_path}")
        print(f"[model] device: {device_map}")
        self.model = Qwen3ASRModel.from_pretrained(
            str(model_path),
            dtype=dtype,
            device_map=device_map,
            max_inference_batch_size=int(self.config.get("qwen_asr_max_inference_batch_size", 1)),
            max_new_tokens=int(self.config.get("qwen_asr_max_new_tokens", 256)),
        )
        print("[model] ready")

    def qwen_language(self):
        language = str(self.config.get("qwen_asr_language", "auto")).strip()
        if not language or language.lower() == "auto":
            return None
        return language

    def transcribe(self, wav_path):
        self.load()
        results = self.model.transcribe(audio=str(wav_path), language=self.qwen_language())
        if not results:
            return ""
        result = results[0]
        return str(getattr(result, "text", result)).strip()


def create_asr_engine(config):
    config["asr_runtime_device"] = choose_asr_device_mode(config)
    mode = choose_asr_engine_mode(config)
    config["asr_engine_mode"] = mode
    if mode == "0":
        return SenseVoiceEngine(config)
    return QwenAsrEngine(config, mode)

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
            discover_models(self.config, persist=True)
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
    SYSTEM_AUDIO_KEYWORDS = (
        "loopback",
        "stereo mix",
        "what u hear",
        "wave out",
        "monitor",
        "立体声混音",
        "混音",
    )

    def __init__(self, config):
        self.sd = require_import("sounddevice")
        self.sf = require_import("soundfile")
        self.config = config
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.channels = int(config.get("channels", 1))
        self.pre_roll_seconds = float(config.get("pre_roll_seconds", 0.5))
        self.pre_roll_samples = max(0, int(self.sample_rate * self.pre_roll_seconds))
        self.input_guard = InputGuard(config)
        self.pre_frames = deque()
        self.pre_raw_frames = deque()
        self.pre_frame_samples = 0
        self.frames = []
        self.raw_frames = []
        self.stream = None
        self.system_stream = None
        self.recording = False
        self.active_source = "microphone"
        self.active_device_name = "default microphone"
        self.active_sample_rate = self.sample_rate
        self.started_at = None
        self.lock = threading.Lock()

    @property
    def is_recording(self):
        return self.recording

    @property
    def recording_source(self):
        return self.active_source

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
            mode = "on" if self.input_guard.enabled else "off"
            print(f"[audio] microphone stream ready, pre-roll={self.pre_roll_seconds:.2f}s, input_guard={mode}")

    def find_system_audio_device(self):
        configured = self.config.get("system_audio_device_index", None)
        devices = self.sd.query_devices()
        if configured not in (None, "", "auto"):
            index = int(configured)
            info = devices[index]
            if int(info.get("max_input_channels", 0)) <= 0:
                raise RuntimeError(f"Configured system audio device is not an input device: {index} {info.get('name')}")
            return index, info

        best = None
        for index, info in enumerate(devices):
            if int(info.get("max_input_channels", 0)) <= 0:
                continue
            name = str(info.get("name", ""))
            lower_name = name.lower()
            score = 0
            for keyword in self.SYSTEM_AUDIO_KEYWORDS:
                if keyword in lower_name or keyword in name:
                    score = max(score, 100 if keyword in ("loopback", "stereo mix", "立体声混音") else 70)
            if score <= 0:
                continue
            hostapi_name = ""
            try:
                hostapi_name = self.sd.query_hostapis()[int(info.get("hostapi", -1))].get("name", "")
            except Exception:
                hostapi_name = ""
            if "WASAPI" in hostapi_name:
                score += 10
            if best is None or score > best[0]:
                best = (score, index, info)
        if best is None:
            raise RuntimeError(
                "No system-audio input device found. Enable Stereo Mix/Loopback in Windows Sound settings, "
                "or set system_audio_device_index in config.json."
            )
        return best[1], best[2]

    def start(self, source="microphone"):
        if source == "system":
            return self.start_system_audio()
        return self.start_microphone()

    def start_microphone(self):
        self.ensure_stream()
        with self.lock:
            if self.recording:
                return False
            self.input_guard.reset()
            self.frames = [frame.copy() for frame in self.pre_frames]
            self.raw_frames = [frame.copy() for frame in self.pre_raw_frames]
            self.active_source = "microphone"
            self.active_device_name = "default microphone"
            self.active_sample_rate = self.sample_rate
            self.started_at = time.time()
            self.recording = True
            return True

    def start_system_audio(self):
        with self.lock:
            if self.recording:
                return False
            self.input_guard.reset()
            self.frames = []
            self.raw_frames = []
            self.active_source = "system"
            self.started_at = time.time()
            self.recording = True
        try:
            device_index, info = self.find_system_audio_device()
            max_channels = max(1, int(info.get("max_input_channels", 1)))
            requested_channels = int(self.config.get("system_audio_channels", 2))
            channels = max(1, min(requested_channels, max_channels))
            default_sr = int(float(info.get("default_samplerate", self.sample_rate) or self.sample_rate))
            requested_sr = int(self.config.get("system_audio_sample_rate", self.sample_rate))
            self.active_device_name = str(info.get("name", f"device {device_index}"))
            self.system_stream = self._open_system_stream(device_index, channels, requested_sr, default_sr)
            self.system_stream.start()
            print(f"[audio] system stream ready, device={device_index} {self.active_device_name}, sample_rate={self.active_sample_rate}, channels={channels}")
            return True
        except Exception:
            with self.lock:
                self.recording = False
                self.frames = []
                self.raw_frames = []
                self.active_source = "microphone"
            raise

    def _open_system_stream(self, device_index, channels, requested_sr, default_sr):
        last_error = None
        for sample_rate in dict.fromkeys([requested_sr, default_sr, self.sample_rate]):
            try:
                stream = self.sd.InputStream(
                    samplerate=int(sample_rate),
                    channels=channels,
                    dtype="float32",
                    device=device_index,
                    callback=self._system_callback,
                )
                self.active_sample_rate = int(sample_rate)
                return stream
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Could not open system audio device: {last_error}")

    def _trim_pre_roll_locked(self):
        while self.pre_frame_samples > self.pre_roll_samples and self.pre_frames:
            old = self.pre_frames.popleft()
            self.pre_raw_frames.popleft()
            self.pre_frame_samples -= old.shape[0]

    def _to_mono_if_needed(self, chunk):
        audio = np.asarray(chunk, dtype=np.float32)
        if bool(self.config.get("system_audio_downmix_to_mono", True)) and audio.ndim == 2 and audio.shape[1] > 1:
            return np.mean(audio, axis=1, keepdims=True).astype(np.float32)
        return audio.copy()

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"[audio] {status}")
        raw_chunk = indata.copy()
        processed_chunk = self.input_guard.process_chunk(raw_chunk)
        with self.lock:
            if self.pre_roll_samples > 0:
                self.pre_frames.append(processed_chunk.copy())
                self.pre_raw_frames.append(raw_chunk.copy())
                self.pre_frame_samples += processed_chunk.shape[0]
                self._trim_pre_roll_locked()
            if self.recording and self.active_source == "microphone":
                self.frames.append(processed_chunk.copy())
                self.raw_frames.append(raw_chunk.copy())

    def _system_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[system-audio] {status}")
        raw_chunk = self._to_mono_if_needed(indata)
        processed_chunk = self.input_guard.process_chunk(raw_chunk)
        with self.lock:
            if self.recording and self.active_source == "system":
                self.frames.append(processed_chunk.copy())
                self.raw_frames.append(raw_chunk.copy())

    def stop_to_wav(self):
        system_stream = None
        with self.lock:
            if not self.recording:
                empty_stats = {"enabled": self.input_guard.enabled, "mode": "input_guard_only" if self.input_guard.enabled else "off", "source": self.active_source, "raw_rms": 0.0, "raw_peak": 0.0, "guarded_rms": 0.0, "guarded_peak": 0.0, "processed_rms": 0.0, "processed_peak": 0.0}
                return None, 0.0, 0.0, 0.0, empty_stats
            self.recording = False
            duration = time.time() - (self.started_at or time.time())
            frames = [frame.copy() for frame in self.frames]
            raw_frames = [frame.copy() for frame in self.raw_frames]
            source = self.active_source
            device_name = self.active_device_name
            sample_rate = self.active_sample_rate
            if source == "system":
                system_stream = self.system_stream
                self.system_stream = None
            self.frames = []
            self.raw_frames = []
            self.active_source = "microphone"
            self.active_device_name = "default microphone"
            self.active_sample_rate = self.sample_rate
        if system_stream is not None:
            try:
                system_stream.stop()
                system_stream.close()
            except Exception as exc:
                print(f"[system-audio] stream close warning: {exc}")
        if not frames:
            empty_stats = {"enabled": self.input_guard.enabled, "mode": "input_guard_only" if self.input_guard.enabled else "off", "source": source, "device": device_name, "sample_rate": sample_rate, "raw_rms": 0.0, "raw_peak": 0.0, "guarded_rms": 0.0, "guarded_peak": 0.0, "processed_rms": 0.0, "processed_peak": 0.0}
            return None, duration, 0.0, 0.0, empty_stats
        audio = np.concatenate(frames, axis=0)
        raw_audio = np.concatenate(raw_frames, axis=0) if raw_frames else audio
        raw_rms = audio_rms(raw_audio)
        guarded_rms = audio_rms(audio)
        raw_peak = float(np.max(np.abs(raw_audio))) if raw_audio.size else 0.0
        guarded_peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        audio_stats = {
            "enabled": bool(self.input_guard.enabled),
            "mode": "input_guard_only" if self.input_guard.enabled else "off",
            "source": source,
            "device": device_name,
            "sample_rate": sample_rate,
            "raw_rms": raw_rms,
            "raw_peak": raw_peak,
            "guarded_rms": guarded_rms,
            "guarded_peak": guarded_peak,
            "processed_rms": guarded_rms,
            "processed_peak": guarded_peak,
            "input_limiter_peak_dbfs": float(self.config.get("audio_input_limiter_peak_dbfs", -1.0)),
        }
        fd, name = tempfile.mkstemp(prefix="sensevoice_ime_", suffix=".wav")
        os.close(fd)
        self.sf.write(name, audio, sample_rate)
        return Path(name), duration, raw_rms, guarded_rms, audio_stats

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


class VoiceStateBus:
    def __init__(self):
        self.subscribers = []
        self.lock = threading.Lock()

    def publish(self, payload):
        with self.lock:
            subscribers = list(self.subscribers)
        for subscriber in subscribers:
            subscriber.put(payload)

    def subscribe(self):
        subscriber = queue.Queue()
        with self.lock:
            self.subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber):
        with self.lock:
            if subscriber in self.subscribers:
                self.subscribers.remove(subscriber)


class ImeApp:
    def __init__(self, config):
        self.config = config
        self.state_bus = VoiceStateBus()
        self.phrases = load_phrases()
        self.engine = create_asr_engine(config)
        self.optimizer_lock = threading.RLock()
        self.text_optimizer = TextOptimizer(config, choose_text_optimizer_mode(config))
        self.noise_suppressor = NoiseSuppressor(config, CONFIG_PATH.parent)
        self.output_polish = OutputPolish(config)
        self.recorder = Recorder(config)
        self.jobs = queue.Queue()
        self.busy = False
        self.normalized_push_to_talk = None
        self.normalized_system_audio_hotkey = None

    def print_help(self):
        print("SenseVoice IME MVP")
        print(f"  Toggle microphone : {self.config.get('push_to_talk_hotkey', 'f8')}")
        print(f"  Toggle system audio: {self.config.get('system_audio_hotkey', 'f9')}")
        print(f"  Reload phrases   : {self.config.get('reload_phrases_hotkey', 'f6')}")
        print(f"  Open phrases     : {self.config.get('open_phrases_hotkey', 'f7')}")
        print("  Rechoose model   : type qqq + Enter in this terminal")
        print("  Quit             : esc")
        print(f"  ASR engine       : {self.engine.name}")
        print(f"  ASR device       : {getattr(self.engine, 'device', self.config.get('device', 'auto'))}")
        print(f"  Text optimizer   : {self.text_optimizer.name}")
        print(f"  Input guard      : {'on' if self.recorder.input_guard.enabled else 'off'}")
        print(f"  Noise suppressor : {'FRCRN (lazy load)' if self.noise_suppressor.enabled else 'off'}")
        print(f"  Output polish    : {'on' if self.output_polish.enabled else 'off'}")
        print(f"  Phrases file     : {PHRASES_PATH}")
        print(f"  Raw ASR log      : {resolve_project_path(self.config.get('raw_transcripts_path'), RAW_TRANSCRIPTS_PATH)}")
        print("")

    def start(self):
        keyboard = require_import("keyboard")
        self.print_help()
        self.engine.load()
        self.text_optimizer.load()
        self.recorder.ensure_stream()
        push_to_talk = self.config.get("push_to_talk_hotkey", "f8")
        system_audio_hotkey = self.config.get("system_audio_hotkey", "f9")
        self.register_push_to_talk(keyboard, push_to_talk)
        self.register_system_audio_hotkey(keyboard, system_audio_hotkey)
        keyboard.add_hotkey(self.config.get("reload_phrases_hotkey", "ctrl+alt+r"), self.reload_phrases)
        keyboard.add_hotkey(self.config.get("open_phrases_hotkey", "ctrl+alt+p"), self.open_phrases_file)
        worker = threading.Thread(target=self.worker_loop, daemon=True)
        worker.start()
        command_listener = threading.Thread(target=self.command_loop, daemon=True)
        command_listener.start()
        print("[ready] Put your cursor in any text box, press the hotkey once to record, press it again to transcribe.")
        keyboard.wait("esc")
        print("[quit]")

    def register_push_to_talk(self, keyboard, hotkey):
        normalized = normalize_hotkey_for_keyboard(hotkey)
        self.normalized_push_to_talk = normalized
        keyboard.add_hotkey(
            normalized,
            lambda: self.toggle_recording("microphone"),
            suppress=bool(self.config.get("hotkey_suppress", False)),
            trigger_on_release=False,
        )
        print(f"[hotkey] registered microphone toggle as {normalized} (suppress={bool(self.config.get('hotkey_suppress', False))})")

    def register_system_audio_hotkey(self, keyboard, hotkey):
        normalized = normalize_hotkey_for_keyboard(hotkey)
        self.normalized_system_audio_hotkey = normalized
        keyboard.add_hotkey(
            normalized,
            lambda: self.toggle_recording("system"),
            suppress=bool(self.config.get("hotkey_suppress", False)),
            trigger_on_release=False,
        )
        print(f"[hotkey] registered system-audio toggle as {normalized} (suppress={bool(self.config.get('hotkey_suppress', False))})")


    def toggle_recording(self, source="microphone"):
        if self.recorder.is_recording:
            active_source = self.recorder.recording_source
            if active_source == source:
                self.stop_recording_if_needed(source=source, force=True)
            else:
                print(f"[recording] already recording ({active_source}); press its hotkey to stop first")
            return
        self.start_recording(source)

    def hotkey_for_source(self, source):
        if source == "system":
            return self.normalized_system_audio_hotkey
        return self.normalized_push_to_talk

    def start_recording(self, source="microphone"):
        if source == "microphone" and self.normalized_system_audio_hotkey:
            try:
                keyboard = require_import("keyboard")
                if keyboard.is_pressed(self.normalized_system_audio_hotkey):
                    return
            except Exception:
                pass
        if self.busy:
            print("[busy] transcription is still running")
            return
        if self.recorder.is_recording:
            return
        try:
            started = self.recorder.start(source=source)
        except Exception as exc:
            print(f"[recording] failed to start {source}: {exc}")
            return
        if started:
            start_sound = self.config.get("sound_on_start", True)
            if start_sound is not False:
                play_sound(start_sound, default_freq=880, default_duration=0.08)
            print(f"[recording] started ({source})")
            self.state_bus.publish({
                "status": "recording",
                "source": source,
                "hint": "正在录音",
                "title": "正在录音",
                "subtitle": "声音输入中",
            })
            max_seconds = float(self.config.get("max_record_seconds", 60))
            threading.Timer(max_seconds, lambda: self.stop_recording_if_needed(source=source, force=True)).start()

    def stop_recording_if_needed(self, source=None, force=False):
        if not self.recorder.is_recording:
            return
        active_source = self.recorder.recording_source
        if source and source != active_source:
            return
        if not force:
            debounce_seconds = float(self.config.get("hotkey_release_debounce_seconds", 0.12))
            if debounce_seconds > 0:
                time.sleep(debounce_seconds)
            try:
                keyboard = require_import("keyboard")
                active_hotkey = self.hotkey_for_source(active_source)
                if active_hotkey and keyboard.is_pressed(active_hotkey):
                    print("[hotkey] ignored release bounce")
                    return
            except Exception:
                pass
        stop_sound = self.config.get("sound_on_stop", True)
        if stop_sound is not False:
            play_sound(stop_sound, default_freq=440, default_duration=0.12)
        wav_path, duration, rms, processed_rms, audio_stats = self.recorder.stop_to_wav()
        print(f"[recording] stopped after {duration:.1f}s, rms={rms:.4f}, processed_rms={processed_rms:.4f}")
        self.state_bus.publish({
            "status": "processing",
            "source": active_source,
            "hint": "正在识别",
            "title": "识别中",
            "subtitle": "请稍候",
        })
        min_seconds = float(self.config.get("min_record_seconds", 0.3))
        if not wav_path or duration < min_seconds:
            print("[skip] recording too short")
            self.state_bus.publish({"status": "idle", "hint": "录音太短，已跳过"})
            return
        min_rms = float(self.config.get("min_rms", 0.0))
        if audio_stats.get("source") == "system":
            min_rms = float(self.config.get("system_audio_min_rms", min_rms))
        if rms < min_rms:
            print(f"[skip] audio too quiet, rms {rms:.4f} < {min_rms:.4f}")
            Path(wav_path).unlink(missing_ok=True)
            self.state_bus.publish({"status": "idle", "hint": "声音太小，已跳过"})
            return
        self.jobs.put((wav_path, duration, rms, processed_rms, audio_stats))

    def prepare_audio_for_asr(self, wav_path, audio_stats):
        cleanup_paths = []
        current_path = Path(wav_path)
        denoise_stats = {"enabled": False, "model": "off"}
        try:
            current_path, denoise_stats, denoise_created = self.noise_suppressor.enhance(current_path)
            if denoise_created:
                cleanup_paths.append(current_path)
        except Exception as exc:
            denoise_stats = {"enabled": bool(self.noise_suppressor.enabled), "model": "FRCRN", "error": str(exc)}
            print(f"[denoise] failed, using guarded audio: {exc}")
            current_path = Path(wav_path)

        data, sample_rate = self.recorder.sf.read(str(current_path), dtype="float32", always_2d=True)
        final_audio = self.output_polish.process_audio(data)
        final_rms = audio_rms(final_audio)
        final_peak = float(np.max(np.abs(final_audio))) if final_audio.size else 0.0
        audio_stats.update({
            "denoise": denoise_stats,
            "output_polish_enabled": bool(self.output_polish.enabled),
            "output_gain_db": float(audio_stats.get("output_gain_db", 0.0)),
            "processed_rms": final_rms,
            "processed_peak": final_peak,
        })
        if self.output_polish.enabled:
            audio_stats["output_gain_db"] = float(audio_stats.get("output_gain_db", 0.0))
            try:
                from tools.audio_processor import linear_to_db
                audio_stats["output_gain_db"] = linear_to_db(self.output_polish.current_gain)
            except Exception:
                pass
            fd, name = tempfile.mkstemp(prefix="sensevoice_ime_polished_", suffix=".wav")
            os.close(fd)
            self.recorder.sf.write(name, final_audio, sample_rate)
            final_path = Path(name)
            cleanup_paths.append(final_path)
            return final_path, audio_stats, cleanup_paths
        return current_path, audio_stats, cleanup_paths
    def worker_loop(self):
        while True:
            wav_path, duration, rms, processed_rms, audio_stats = self.jobs.get()
            cleanup_paths = []
            self.busy = True
            try:
                print("[transcribe] working...")
                asr_wav_path, audio_stats, cleanup_paths = self.prepare_audio_for_asr(wav_path, audio_stats)
                processed_rms = float(audio_stats.get("processed_rms", processed_rms))
                asr_text = self.engine.transcribe(asr_wav_path)
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
                    "processed_rms": round(float(processed_rms), 6),
                    "audio_processing": audio_stats,
                    "asr_engine": self.engine.name,
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
                self.state_bus.publish({
                    "status": "done",
                    "text": text,
                    "source": audio_stats.get("source", "microphone"),
                    "hint": "识别完成",
                    "title": "完成",
                    "subtitle": "文本已输出",
                })
            except Exception as exc:
                print(f"[error] {exc}")
                self.state_bus.publish({"status": "idle", "hint": f"错误：{exc}"})
            finally:
                try:
                    Path(wav_path).unlink(missing_ok=True)
                    for extra_path in cleanup_paths:
                        Path(extra_path).unlink(missing_ok=True)
                except Exception:
                    pass
                self.busy = False
                self.jobs.task_done()
                if not self.recorder.is_recording:
                    self.state_bus.publish({"status": "idle", "hint": "按快捷键开始录音"})

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

    def runtime_snapshot(self):
        return {
            "audio_processing_enabled": bool(self.config.get("audio_processing_enabled", True)),
            "noise_suppression_enabled": bool(self.config.get("noise_suppression_enabled", False)),
            "asr_device_mode": str(self.config.get("asr_device_mode", self.config.get("asr_device_default", "1"))),
            "asr_engine_mode": str(self.config.get("asr_engine_mode", self.config.get("asr_engine_default", "0"))),
            "text_optimizer_default": str(self.text_optimizer.mode),
            "text_optimizer_name": self.text_optimizer.name,
            "asr_engine_name": self.engine.name,
            "busy": bool(self.busy),
            "recording": bool(self.recorder.is_recording),
        }

    def apply_runtime_config(self, updates):
        if self.recorder.is_recording or self.busy:
            raise RuntimeError("当前正在录音或识别，等空闲后再切换模型相关选项。")

        changed = {}

        if "audio_processing_enabled" in updates:
            enabled = bool(updates["audio_processing_enabled"])
            self.config["audio_processing_enabled"] = enabled
            self.recorder.input_guard.enabled = enabled
            self.output_polish.enabled = enabled and bool(self.config.get("audio_output_polish_enabled", True))
            changed["audio_processing_enabled"] = enabled

        if "noise_suppression_enabled" in updates:
            enabled = bool(updates["noise_suppression_enabled"])
            self.config["noise_suppression_enabled"] = enabled
            self.noise_suppressor.enabled = enabled
            changed["noise_suppression_enabled"] = enabled

        if "text_optimizer_default" in updates:
            mode = str(updates["text_optimizer_default"])
            if mode not in TextOptimizer.MODES:
                raise ValueError("text_optimizer_default must be 0, 1, or 2")
            self.set_text_optimizer_mode(mode)
            self.config["text_optimizer_default"] = mode
            changed["text_optimizer_default"] = mode

        if "asr_device_mode" in updates:
            mode = str(updates["asr_device_mode"])
            if mode not in {"0", "1"}:
                raise ValueError("asr_device_mode must be 0 or 1")
            self.config["asr_device_default"] = mode
            self.config["asr_device_mode"] = mode
            self.config["device"] = "cuda:0" if mode == "1" else "cpu"
            changed["asr_device_mode"] = mode

        if "asr_engine_mode" in updates:
            mode = str(updates["asr_engine_mode"])
            if mode not in {"0", "1", "2"}:
                raise ValueError("asr_engine_mode must be 0, 1, or 2")
            self.config["asr_engine_default"] = mode
            self.config["asr_engine_mode"] = mode
            self.engine = SenseVoiceEngine(self.config) if mode == "0" else QwenAsrEngine(self.config, mode)
            changed["asr_engine_mode"] = mode
            changed["asr_engine_name"] = self.engine.name

        if changed:
            save_config(self.config)
        return {"changed": changed, "config": self.runtime_snapshot()}

    def set_text_optimizer_mode(self, new_mode):
        current_mode = self.text_optimizer.mode
        if new_mode == current_mode:
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
                self.config["text_optimizer_default"] = "0"
                print("[optimizer] switched to off")
                raise
        print(f"[optimizer] switched to {self.text_optimizer.name}")

    def rechoose_text_optimizer(self):
        current_mode = self.text_optimizer.mode
        new_mode = choose_text_optimizer_mode(self.config, current_mode=current_mode)
        if new_mode == current_mode:
            print(f"[optimizer] unchanged: {self.text_optimizer.name}")
            return
        try:
            self.set_text_optimizer_mode(new_mode)
        except Exception:
            return

    def reload_phrases(self):
        self.phrases = load_phrases()
        print(f"[phrases] loaded {len(self.phrases)} item(s)")

    def open_phrases_file(self):
        if not PHRASES_PATH.exists():
            PHRASES_PATH.write_text("[]\n", encoding="utf-8")
        os.startfile(str(PHRASES_PATH))
        print(f"[phrases] opened {PHRASES_PATH}")


def make_control_handler(app):
    class ControlHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FRONTEND_PATH), **kwargs)

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            super().end_headers()

        def do_OPTIONS(self):
            self.send_response(204)
            self.end_headers()

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/config":
                self.write_json({"ok": True, "config": app.runtime_snapshot()})
                return
            if path == "/events":
                self.stream_events()
                return
            if path == "/":
                self.path = "/index.html"
            super().do_GET()

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            if path != "/api/config":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                payload = json.loads(raw or "{}")
                result = app.apply_runtime_config(payload)
                self.write_json({"ok": True, **result})
                app.state_bus.publish({"status": "idle", "hint": "设置已更新"})
            except Exception as exc:
                self.write_json({"ok": False, "error": str(exc)}, status=400)

        def stream_events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            subscriber = app.state_bus.subscribe()
            try:
                self.write_event({"status": "idle", "hint": "已连接 SenseVoice IME"})
                while True:
                    self.write_event(subscriber.get())
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                app.state_bus.unsubscribe(subscriber)

        def write_event(self, payload):
            data = json.dumps(payload, ensure_ascii=False)
            self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
            self.wfile.flush()

        def write_json(self, payload, status=200):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            return

    return ControlHandler


def start_control_server(app, host="127.0.0.1", port=8765):
    if not FRONTEND_PATH.exists():
        raise FileNotFoundError(f"Frontend folder does not exist: {FRONTEND_PATH}")
    server = ThreadingHTTPServer((host, port), make_control_handler(app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


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
    wav_path, duration, rms, processed_rms, audio_stats = app.recorder.stop_to_wav()
    print(f"[recording] stopped after {duration:.1f}s, rms={rms:.4f}, processed_rms={processed_rms:.4f}")
    min_rms = float(config.get("min_rms", 0.0))
    if rms < min_rms:
        print(f"[skip] audio too quiet, rms {rms:.4f} < {min_rms:.4f}")
        Path(wav_path).unlink(missing_ok=True)
        return
    asr_wav_path, audio_stats, cleanup_paths = app.prepare_audio_for_asr(wav_path, audio_stats)
    processed_rms = float(audio_stats.get("processed_rms", processed_rms))
    asr_text = app.engine.transcribe(asr_wav_path)
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
        "processed_rms": round(float(processed_rms), 6),
        "audio_processing": audio_stats,
        "asr_engine": app.engine.name,
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
    for extra_path in cleanup_paths:
        Path(extra_path).unlink(missing_ok=True)


def main():
    global CONFIG_PATH
    parser = argparse.ArgumentParser(description="Minimal SenseVoice push-to-talk dictation IME for Windows.")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to config.json")
    parser.add_argument("--list-devices", action="store_true", help="Print audio devices and exit")
    parser.add_argument("--test-model", action="store_true", help="Run SenseVoice on bundled zh.mp3")
    parser.add_argument("--once", type=float, default=0, help="Record a fixed number of seconds, transcribe, then exit")
    parser.add_argument("--no-paste", action="store_true", help="Do not paste result into the active input")
    parser.add_argument("--ui", action="store_true", help="Start the local web control panel")
    parser.add_argument("--ui-port", type=int, default=8765, help="Port for the local web control panel")
    args = parser.parse_args()

    CONFIG_PATH = Path(args.config)
    config = load_config()

    try:
        if args.list_devices:
            list_devices()
        elif args.test_model:
            test_model(config)
        elif args.once > 0:
            config["audio_processing_enabled"] = choose_audio_processing_mode(config)
            config["noise_suppression_enabled"] = choose_noise_suppression_mode(config)
            record_once(config, args.once, not args.no_paste)
        else:
            if args.ui:
                config["prompt_audio_processing_on_start"] = False
                config["prompt_noise_suppression_on_start"] = False
                config["prompt_asr_device_on_start"] = False
                config["prompt_asr_engine_on_start"] = False
                config["prompt_text_optimizer_on_start"] = False
            config["audio_processing_enabled"] = choose_audio_processing_mode(config)
            config["noise_suppression_enabled"] = choose_noise_suppression_mode(config)
            app = ImeApp(config)
            if args.ui:
                server = start_control_server(app, port=args.ui_port)
                url = f"http://127.0.0.1:{args.ui_port}/?connect=1"
                print(f"[ui] control panel: {url}")
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
            app.start()
    except MissingDependency as exc:
        print(f"[dependency] {exc}")
        return 2
    except KeyboardInterrupt:
        print("[quit]")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
