# Portable build notes

## Practical target

Recommended shape:

```text
SenseVoiceIME/
  SenseVoiceIME.exe
  .venv/
  desktop_app.py
  sensevoice_ime.py
  tools/
  config.json
  phrases.json
```

Models do not need to be inside this folder. The app scans common local model locations on startup and can update `config.json` automatically.

## Why not one huge EXE by default?

Torch, FunASR, ModelScope, Transformers, CUDA-related DLLs, and audio libraries are large and sensitive to PyInstaller hooks. A true single-file EXE is possible in principle, but it can be hundreds of MB or larger, unpack slowly on every launch, and often needs per-machine testing.

The current `SenseVoiceIME.exe` is a lightweight launcher. It gives the user a normal EXE entry while reusing the project virtual environment and local model cache.

## Model auto scan

The app scans:

- `model/` near the project
- user ModelScope cache: `%USERPROFILE%\.cache\modelscope\hub\models`
- user Hugging Face cache: `%USERPROFILE%\.cache\huggingface\hub`
- common drive folders such as `D:\models`, `E:\Projects\ai`, `E:\model`

It looks for:

- SenseVoiceSmall
- Qwen3-0.6B
- Qwen3-1.7B
- Qwen3-ASR-0.6B
- Qwen3-ASR-1.7B
- FRCRN noise suppression model

## Rebuild launcher EXE

```powershell
.\build_launcher_exe.bat
```

## Toward a true all-in-one EXE

If you still want a true single EXE, build it on the target Python environment with PyInstaller and then test on a clean Windows machine. Expect to add hidden imports and collect rules for `torch`, `funasr`, `modelscope`, `transformers`, `qwen_asr`, `sounddevice`, and native DLLs.
