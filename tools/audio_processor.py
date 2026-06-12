"""Audio dynamics tools for SenseVoice IME.

Recommended signal order:
    microphone -> InputGuard -> optional denoise -> OutputPolish -> ASR

InputGuard is intentionally tiny and real-time safe: DC offset removal + limiter.
OutputPolish runs after denoise: slow AGC + compressor + final limiter.
"""

import numpy as np


def choose_audio_processing_mode(config):
    default_enabled = bool(config.get("audio_processing_enabled", True))
    if not bool(config.get("prompt_audio_processing_on_start", True)):
        return default_enabled
    print("Microphone input guard / output polish:")
    print("  0 = off / raw microphone signal")
    print("  1 = on / input limiter + post-denoise AGC/compressor")
    default_choice = "1" if default_enabled else "0"
    try:
        choice = input(f"Choose audio processing [0/1, default {default_choice}]: ").strip()
    except EOFError:
        choice = ""
    if choice == "0":
        return False
    if choice == "1":
        return True
    return default_enabled


def audio_rms(audio):
    return float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0


def db_to_linear(db):
    return float(10 ** (float(db) / 20.0))


def linear_to_db(value):
    value = max(float(value), 1e-8)
    return float(20.0 * np.log10(value))


class InputGuard:
    """Real-time microphone guard: DC offset removal + limiter only."""

    def __init__(self, config):
        self.config = config
        self.enabled = bool(config.get("audio_processing_enabled", True))
        self.limiter_peak = db_to_linear(config.get("audio_input_limiter_peak_dbfs", -1.0))

    def reset(self):
        pass

    def process_chunk(self, chunk):
        raw = np.asarray(chunk, dtype=np.float32)
        if not self.enabled or not raw.size:
            return raw.copy()
        processed = raw.copy()
        processed = processed - np.mean(processed, axis=0, keepdims=True)
        peak = float(np.max(np.abs(processed))) if processed.size else 0.0
        if peak > self.limiter_peak:
            processed *= self.limiter_peak / peak
        return np.clip(processed, -self.limiter_peak, self.limiter_peak).astype(np.float32)


class OutputPolish:
    """Post-denoise dynamics: slow AGC + compressor + final limiter."""

    def __init__(self, config):
        self.config = config
        self.enabled = bool(config.get("audio_processing_enabled", True)) and bool(config.get("audio_output_polish_enabled", True))
        self.target_rms = db_to_linear(config.get("audio_target_rms_dbfs", -18.0))
        self.threshold = db_to_linear(config.get("audio_compressor_threshold_dbfs", -10.0))
        self.ratio = max(float(config.get("audio_compressor_ratio", 4.0)), 1.0)
        self.limiter_peak = db_to_linear(config.get("audio_limiter_peak_dbfs", -1.0))
        self.max_boost = db_to_linear(config.get("audio_max_boost_db", 18.0))
        self.max_cut = db_to_linear(config.get("audio_max_cut_db", -18.0))
        self.noise_floor = float(config.get("audio_noise_floor_rms", 0.0015))
        self.current_gain = 1.0

    def reset(self):
        self.current_gain = 1.0

    def process_audio(self, audio):
        raw = np.asarray(audio, dtype=np.float32)
        if not self.enabled or not raw.size:
            return raw.copy()

        processed = raw.copy()
        processed = processed - np.mean(processed, axis=0, keepdims=True)
        rms = audio_rms(processed)
        if rms < self.noise_floor:
            gain = 1.0
        else:
            gain = float(np.clip(self.target_rms / max(rms, 1e-8), self.max_cut, self.max_boost))
        self.current_gain = gain
        processed *= gain

        abs_audio = np.abs(processed)
        over = abs_audio > self.threshold
        if np.any(over):
            compressed = self.threshold + (abs_audio[over] - self.threshold) / self.ratio
            processed[over] = np.sign(processed[over]) * compressed

        peak = float(np.max(np.abs(processed))) if processed.size else 0.0
        if peak > self.limiter_peak:
            processed *= self.limiter_peak / peak

        return np.clip(processed, -self.limiter_peak, self.limiter_peak).astype(np.float32)


def summarize_audio_processing(raw_audio, guarded_audio, final_audio, input_guard, output_polish):
    raw_rms = audio_rms(raw_audio)
    guarded_rms = audio_rms(guarded_audio)
    final_rms = audio_rms(final_audio)
    raw_peak = float(np.max(np.abs(raw_audio))) if raw_audio.size else 0.0
    guarded_peak = float(np.max(np.abs(guarded_audio))) if guarded_audio.size else 0.0
    final_peak = float(np.max(np.abs(final_audio))) if final_audio.size else 0.0
    return {
        "enabled": bool(input_guard.enabled),
        "mode": "input_guard_then_optional_denoise_then_output_polish" if input_guard.enabled else "off",
        "raw_rms": raw_rms,
        "raw_peak": raw_peak,
        "guarded_rms": guarded_rms,
        "guarded_peak": guarded_peak,
        "processed_rms": final_rms,
        "processed_peak": final_peak,
        "input_limiter_peak_dbfs": float(input_guard.config.get("audio_input_limiter_peak_dbfs", -1.0)),
        "output_polish_enabled": bool(output_polish.enabled),
        "output_gain_db": linear_to_db(output_polish.current_gain),
        "target_rms_dbfs": float(output_polish.config.get("audio_target_rms_dbfs", -18.0)),
        "limiter_peak_dbfs": float(output_polish.config.get("audio_limiter_peak_dbfs", -1.0)),
    }
