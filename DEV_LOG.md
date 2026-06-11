# SenseVoice IME DEV_LOG

## 1.0.0 - Local LLM Text Optimization Release

Date: 2026-06-11

This release turns the MVP into a complete local dictation workflow: SenseVoice handles ASR, phrase rules handle deterministic corrections, and optional Qwen3 models improve the recognized text before paste.

### Added

- Added `TextOptimizer` with three startup modes:
  - `0`: off, keep the original behavior.
  - `1`: local `Qwen3-0.6B` text optimization.
  - `2`: local `Qwen3-1.7B` text optimization.
- Added Qwen model paths to `config.json`:
  - `qwen_0_6b_path`
  - `qwen_1_7b_path`
- Added `text_optimizer_default`, `prompt_text_optimizer_on_start`, and `text_optimizer_max_new_tokens`.
- Added runtime command listener. Typing `qqq` in the terminal reopens the optimizer selection menu without restarting the program.
- Added model unloading and CUDA cache cleanup when switching optimizers.
- Added `transformers` dependency for local Qwen inference.
- Expanded `phrases.json` for personal/technical terminology corrections.
- Restored and refreshed `README.md` and `README_CN.md` for the 1.0.0 workflow.

### Changed

- Recognition pipeline is now:

```text
SenseVoice ASR -> phrases.json replacements -> optional Qwen optimizer -> paste
```

- The Qwen prompt is intentionally short and conservative: fix ASR errors, typos, homophones, punctuation, and sentence breaks; do not expand or explain.
- The text optimizer uses `local_files_only=True` so it does not silently download models at runtime.
- The app now prints the selected optimizer in the startup help.

### Validation

- Verified both local Qwen directories contain required files.
- Verified Transformers can read tokenizer/config for:
  - `model/千问3-0.6B`
  - `model/千问3-1.7B`
- Ran Python syntax check:

```powershell
python -m py_compile sensevoice_ime.py
```

### Notes

- The `model/` directory remains ignored by git. Local model weights are not uploaded.
- Qwen3-1.7B gives better corrections for mixed Chinese/English technical speech, while Qwen3-0.6B is faster.

## Earlier Milestones

### v0.3.3 - Sound Cues

- Added optional start/stop sound cues.
- Supported built-in beep, silence, or custom WAV files through `config.json`.

### v0.3.2 - Hotkey Suppression And Config Hardening

- Added `suppress=True` so the push-to-talk hotkey is consumed before focused apps see it.
- Added safer defaults for minimum recording length, maximum recording length, clipboard behavior, and spacing.

### v0.3.1 - Hotkey Conflict Documentation

- Documented known hotkey conflicts and workarounds.

### v0.3.0 - Push-To-Talk

- Added hold-to-record and release-to-transcribe workflow.
- Normalized the backtick key to `grave` for the Python `keyboard` package.

### v0.2.x - SenseVoice Pipeline

- Added local SenseVoiceSmall inference through FunASR.
- Added microphone recording, temporary WAV generation, phrase replacement, and paste output.
- Added RMS quiet-audio guard.

### v0.1.0 - Standalone MVP

- Created the standalone Python MVP with config, phrase rules, run scripts, and dependency list.
