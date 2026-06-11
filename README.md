# SenseVoice IME

SenseVoice IME is a small Windows push-to-talk dictation tool. It records your voice while you hold a hotkey, transcribes it with a local SenseVoiceSmall model, optionally improves the text with a local Qwen3 model, and pastes the result into the active input box.

Current version: `1.1.0`

## Highlights

- Local-first speech recognition with `model/SenseVoiceSmall`.
- Push-to-talk recording with the backtick/grave key by default.
- Automatic clipboard paste into the focused text box.
- Editable phrase replacement rules in `phrases.json`; this shared hotword library is tracked and uploaded with the repository.
- Optional local text optimization after ASR:
  - `0`: off, keep the raw SenseVoice flow.
  - `1`: use `Qwen3-0.6B`.
  - `2`: use `Qwen3-1.7B`.
- Runtime model switching: type `qqq` in the terminal and press Enter to choose `0/1/2` again.
- Start/stop sound cues, configurable in `config.json`.
- Quiet-audio guard with an RMS threshold to reduce accidental hallucinated text.
- Raw ASR logging to `raw_transcripts.jsonl` before Qwen optimization for review and fine-tuning samples.
- Chinese/English output restriction to filter accidental Korean/Japanese script hallucinations from auto language detection.
- Pre-roll audio buffering and hotkey release debounce to reduce clipped starts and random stop events.

## Requirements

- Windows.
- Python 3.11 recommended.
- A local SenseVoiceSmall model at:

```text
model/SenseVoiceSmall
```

- Optional local Qwen3 models at:

```text
model/千问3-0.6B
model/千问3-1.7B
```

The `model/` directory is intentionally ignored by git. Models are not uploaded to GitHub.

## Setup

From PowerShell:

```powershell
cd "E:\Projects\ai\sensevoice_ime"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Or create the environment with:

```powershell
.\setup.bat
```

## Run

```powershell
cd "E:\Projects\ai\sensevoice_ime"
.\run.bat
```

When the program starts, choose the text optimizer:

```text
Text optimizer:
  0 = off / keep current behavior
  1 = Qwen3-0.6B
  2 = Qwen3-1.7B
Choose text optimizer [0/1/2, default 0]:
```

Then:

1. Put the cursor in any text box.
2. Hold the backtick key: `` ` ``.
3. Speak.
4. Release the key.
5. Wait for transcription and paste.

Press `Esc` to quit.

## Runtime Commands

Type this in the running terminal and press Enter:

```text
qqq
```

The program will ask you to choose the text optimizer again. This lets you switch between off, Qwen3-0.6B, and Qwen3-1.7B without restarting the app.

## Configuration

Edit `config.json`:

```json
{
  "model_path": "model/SenseVoiceSmall",
  "language": "auto",
  "device": "auto",
  "qwen_0_6b_path": "model/千问3-0.6B",
  "qwen_1_7b_path": "model/千问3-1.7B",
  "prompt_text_optimizer_on_start": true,
  "text_optimizer_default": "0",
  "text_optimizer_max_new_tokens": 128,
  "push_to_talk_hotkey": "`",
  "sound_on_start": "sounds/start.wav",
  "sound_on_stop": "sounds/stop.wav",
  "pre_roll_seconds": 0.5,
  "restrict_output_to_zh_en": true,
  "hotkey_release_debounce_seconds": 0.12,
  "log_raw_transcripts": true,
  "raw_transcripts_path": "raw_transcripts.jsonl"
}
```

Useful fields:

| Key | Meaning |
| --- | --- |
| `model_path` | Local SenseVoiceSmall model path. |
| `device` | `auto` uses CUDA when available, otherwise CPU. |
| `qwen_0_6b_path` | Local Qwen3-0.6B path. |
| `qwen_1_7b_path` | Local Qwen3-1.7B path. |
| `prompt_text_optimizer_on_start` | Ask for `0/1/2` on startup. |
| `text_optimizer_default` | Default optimizer mode. |
| `text_optimizer_max_new_tokens` | Output limit for the text optimizer. |
| `push_to_talk_hotkey` | Hold-to-record hotkey. |
| `reload_phrases_hotkey` | Reload `phrases.json` without restarting. |
| `open_phrases_hotkey` | Open `phrases.json`. |
| `min_rms` | Quiet-audio threshold. |
| `pre_roll_seconds` | Audio buffered before hotkey press to avoid clipped starts. |
| `restrict_output_to_zh_en` | Filter accidental non-Chinese/non-English script output. |
| `hotkey_release_debounce_seconds` | Debounce release events to reduce random recording stops. |
| `log_raw_transcripts` | Record pre-Qwen ASR text for review. |
| `raw_transcripts_path` | JSONL path for raw ASR logs. |

## Phrase Replacements

Edit `phrases.json` to correct repeated ASR mistakes before the optional Qwen pass:

```json
[
  { "spoken": "cloud code", "replace": "Claude Code" },
  { "spoken": "chat G", "replace": "ChatGPT" },
  { "spoken": "sense voice", "replace": "SenseVoice" }
]
```

Reload while the program is running:

```text
Ctrl+Alt+R
```

Open the file while running:

```text
Ctrl+Alt+P
```

## Qwen Model Files

A complete local Qwen model folder should contain files such as:

```text
config.json
tokenizer.json
generation_config.json
model.safetensors
```

or sharded weights such as:

```text
model-00001-of-00002.safetensors
model-00002-of-00002.safetensors
model.safetensors.index.json
```

If you choose `1` or `2` and the folder is incomplete, the app will report the missing file.

## Developer Commands

List audio devices:

```powershell
.\.venv\Scripts\python.exe .\sensevoice_ime.py --list-devices
```

Test the bundled SenseVoice sample:

```powershell
.\.venv\Scripts\python.exe .\sensevoice_ime.py --test-model
```

Record once without pasting:

```powershell
.\.venv\Scripts\python.exe .\sensevoice_ime.py --once 3 --no-paste
```

Syntax check:

```powershell
python -m py_compile sensevoice_ime.py
```

## Project Files

```text
.
|-- sensevoice_ime.py
|-- config.json
|-- phrases.json
|-- requirements.txt
|-- run.bat
|-- setup.bat
|-- test_model.bat
|-- README.md
|-- README_CN.md
|-- DEV_LOG.md
|-- DEV_LOG_CN.md
`-- model/              # ignored by git
```

## Known Limitations

- This is not a native Windows IME driver.
- It uses clipboard paste, so some apps can block or redirect paste.
- The console window must stay open.
- Model loading can take time, especially for Qwen3-1.7B.
- Switching models unloads the previous optimizer and clears CUDA cache when available, but memory behavior still depends on PyTorch and the GPU driver.

## Version 1.0.0

The `1.0.0` release marks the first complete local dictation workflow with optional local LLM text optimization and runtime model switching.

## Changelog

### v1.1.0

- Added raw ASR logging to `raw_transcripts.jsonl`, always recording text before Qwen optimization for review and future fine-tuning samples.
- Added `pre_roll_seconds`, defaulting to 0.5 seconds, to reduce clipped sentence starts.
- Added `restrict_output_to_zh_en` to filter accidental Korean/Japanese script output from SenseVoice auto language detection.
- Added `hotkey_release_debounce_seconds` to reduce random stop/restart behavior while holding the push-to-talk key.
- Added stronger GitHub hotword corrections for `G up`, `Goodub`, `good hub`, `get hub`, `hub 上`, and related variants.
- Expanded `phrases.json` from 36 to 417 personal hotword rules covering Claude Code, ChatGPT, Wwise, WAAPI, SoundBank, TypeScript, UE5, MCP, RAG, and more.
- Fixed phrase replacement ordering by applying longer rules first, preventing short rules such as `chat G` from breaking longer forms such as `chat g p t`.
- Fixed repeated replacement inside already-correct English terms, preventing `GitHub` from becoming `GitGitHub`.
- Fixed raw log worker metadata by passing `duration` and `rms` through the job queue.
- Fixed `run.bat` / `setup.bat` to prefer `.venv` and added the missing `torchaudio` dependency.
- Kept `phrases.json` tracked and uploaded; `raw_transcripts.jsonl` remains ignored to avoid publishing private dictation logs.

### v1.0.0

- Added the complete local SenseVoice + optional Qwen3 text optimization workflow.
- Added startup optimizer selection: off, Qwen3-0.6B, or Qwen3-1.7B.
- Added runtime `qqq` model switching.
- Added sound cues, quiet-audio guard, and editable phrase replacements.
