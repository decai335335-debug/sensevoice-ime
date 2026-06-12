"""Optional FRCRN acoustic noise suppression for SenseVoice IME."""

import tempfile
from pathlib import Path


def choose_noise_suppression_mode(config):
    default_enabled = bool(config.get("noise_suppression_enabled", False))
    if not bool(config.get("prompt_noise_suppression_on_start", True)):
        return default_enabled
    print("Noise suppression model:")
    print("  0 = off / skip FRCRN denoise")
    print("  1 = on / load FRCRN single-mic 16k denoise")
    default_choice = "1" if default_enabled else "0"
    try:
        choice = input(f"Choose noise suppression [0/1, default {default_choice}]: ").strip()
    except EOFError:
        choice = ""
    if choice == "0":
        return False
    if choice == "1":
        return True
    return default_enabled


class NoiseSuppressor:
    def __init__(self, config, config_base_path):
        self.config = config
        self.config_base_path = Path(config_base_path)
        self.enabled = bool(config.get("noise_suppression_enabled", False))
        self.model = None

    def model_path(self):
        raw_path = str(self.config.get("noise_suppression_model_path", "model/FRCRN语音降噪-单麦-16k")).strip()
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self.config_base_path / path
        return path

    def load(self):
        if not self.enabled or self.model is not None:
            return
        model_path = self.model_path()
        if not model_path.exists():
            raise FileNotFoundError(f"Noise suppression model path does not exist: {model_path}")
        from modelscope.pipelines import pipeline
        from modelscope.utils.constant import Tasks
        print(f"[denoise] loading FRCRN from {model_path}")
        self.model = pipeline(Tasks.acoustic_noise_suppression, model=str(model_path))
        print("[denoise] ready")

    def enhance(self, wav_path):
        if not self.enabled:
            return Path(wav_path), {"enabled": False, "model": "off"}, False
        self.load()
        fd, name = tempfile.mkstemp(prefix="sensevoice_ime_denoised_", suffix=".wav")
        try:
            import os
            os.close(fd)
        except Exception:
            pass
        Path(name).unlink(missing_ok=True)
        self.model(str(wav_path), output_path=name)
        return Path(name), {"enabled": True, "model": "FRCRN", "output_path": name}, True

