# SenseVoice IME MVP

A minimal Windows push-to-talk voice input tool that uses a local SenseVoiceSmall model to transcribe speech and paste text into the active input box.

## 1. One-Line Positioning

SenseVoice IME MVP turns your local `iic/SenseVoiceSmall` model into a lightweight voice input method: hold a hotkey, speak, release, and the recognized text is pasted where your cursor is.

## 2. Pain Points Solved

Before this tool:

- Voice recognition required opening a separate transcription app, copying text, and pasting it manually.
- Local SenseVoice models were downloaded but not connected to a daily typing workflow.
- Dictation tools often hid hotkey behavior behind a full desktop app or cloud account.
- Custom words such as product names, project names, and tool names were easy to misrecognize.

Now:

- Hold one hotkey to record, release it to transcribe, and paste automatically.
- The model runs locally from `model/SenseVoiceSmall`.
- Phrase replacements are controlled by a simple JSON file.
- Quiet recordings are skipped to reduce accidental false text.
- The hotkey is **suppressed** so focused apps (e.g. VS Code, Codex, browsers) do not receive the shortcut.

Who this is for:

- Heavy keyboard users who want fast voice input in Obsidian, browser forms, chat boxes, and editors.
- Local AI users who already have SenseVoiceSmall downloaded and want a practical input workflow.
- Developers experimenting with a small, hackable dictation pipeline before building a full IME or Electron UI.

## 3. Core Features

| Feature | Problem It Solves |
| --- | --- |
| Push-to-talk recording | Avoids always-on listening and makes dictation intentional. |
| Release-to-transcribe | Stops recording exactly when the user releases the hotkey, then starts recognition. |
| Local SenseVoiceSmall inference | Uses the existing local model without sending audio to a cloud service. |
| Clipboard paste output | Works with most apps by copying recognized text and sending `Ctrl+V`. |
| Phrase replacements | Fixes recurring vocabulary such as `SenseVoice`, `OpenWhispr`, `Markdown`, and custom project terms. |
| Quiet audio skip | Prevents low-volume background noise from becoming accidental pasted text. |
| Hotkey suppression | Prevents apps like VS Code or Codex from intercepting the push-to-talk shortcut. |
| Configurable hotkeys | Lets users avoid conflicts with apps that already use Ctrl+Backtick. |

## 4. Installation

### Prerequisites

- Windows desktop environment.
- Python 3.11 installed.
- Local model folder exists:

```text
model/SenseVoiceSmall
```

- Python dependencies installed:

```bat
python -m pip install -r requirements.txt
```

Or run the helper script:

```bat
setup.bat
```

The current tested machine already has these dependencies installed:

```text
funasr, modelscope, torch, sounddevice, soundfile, keyboard, pyperclip, numpy
```

### Configure Model Path

Open `config.json` and confirm:

```json
"model_path": "model/SenseVoiceSmall"
```

### Configure Push-To-Talk Hotkey

Default:

```json
"push_to_talk_hotkey": "ctrl+`"
```

The program internally maps the backtick key to `grave`, because the Python `keyboard` package names that key `grave` on Windows.

## 5. Usage

### Scenario 1: Dictate Into Any Text Box

When to use: You want to enter text into Obsidian, a browser, a chat box, or another editor without typing.

1. Run `run.bat`.
2. Wait until the console prints `[model] ready` and `[ready]`.
3. Click the target input box so the cursor is active.
4. Hold <kbd>Ctrl</kbd> + <kbd>`</kbd>.
5. Speak.
6. Release <kbd>Ctrl</kbd> + <kbd>`</kbd>.
7. Wait for `[transcribe] working...` and `[paste] sent to active input`.

### Scenario 2: Add Common Words

When to use: SenseVoice repeatedly writes a project name or technical term incorrectly.

1. Open `phrases.json`, or press `Ctrl+Alt+P` while the program is running.
2. Add a replacement rule:

```json
{ "spoken": "sense voice", "replace": "SenseVoice" }
```

3. Save the file.
4. Press `Ctrl+Alt+R` to reload phrases without restarting.

### Scenario 3: Test The Model Without Recording

When to use: You want to confirm the local model loads correctly.

```bat
python sensevoice_ime.py --test-model
```

Expected output includes:

```text
[model] ready
[test] ...
```

### Scenario 4: Test Recording Without Pasting

When to use: You want to debug microphone input before using it in another app.

```bat
python sensevoice_ime.py --once 3 --no-paste
```

## 6. Configuration Reference (`config.json`)

| Key | Default | Description |
| --- | --- | --- |
| `model_path` | `model/SenseVoiceSmall` | Path to the local SenseVoiceSmall model. |
| `language` | `auto` | Recognition language. `auto` lets the model decide. |
| `device` | `auto` | Inference device. `auto` prefers `cuda:0` if available, otherwise `cpu`. |
| `sample_rate` | `16000` | Microphone sample rate in Hz. |
| `channels` | `1` | Number of recording channels. |
| `push_to_talk_hotkey` | `ctrl+\`` | Hold this hotkey to record. |
| `reload_phrases_hotkey` | `ctrl+alt+r` | Reload `phrases.json` without restarting. |
| `open_phrases_hotkey` | `ctrl+alt+p` | Open `phrases.json` in the default editor. |
| `paste_after_transcribe` | `true` | Automatically paste the result after recognition. |
| `append_space` | `false` | Append a trailing space to the recognized text. |
| `restore_clipboard` | `false` | Restore the previous clipboard content after pasting. |
| `min_record_seconds` | `0.3` | Minimum recording duration; shorter recordings are discarded. |
| `max_record_seconds` | `60` | Maximum recording duration before forced stop. |
| `min_rms` | `0.003` | RMS volume threshold; quieter audio is skipped to avoid false recognition. |

## 7. Tech Stack / Toolchain / Dependencies

| Layer | Technology |
| --- | --- |
| Language | Python 3.11 |
| ASR model | `iic/SenseVoiceSmall` local model |
| ASR runtime | FunASR `AutoModel` |
| Model source | ModelScope local cache |
| Audio capture | `sounddevice` |
| Audio file output | `soundfile` temporary WAV files |
| Hotkeys | Python `keyboard` package |
| Paste bridge | `pyperclip` + synthetic `Ctrl+V` |
| Numeric processing | `numpy` RMS calculation |

| Tool | Purpose |
| --- | --- |
| `run.bat` | Starts the push-to-talk dictation loop. |
| `test_model.bat` | Runs local model verification. |
| `setup.bat` | Creates venv and installs dependencies. |
| `--list-devices` | Lists available microphone devices. |
| `--once N --no-paste` | Records for N seconds and prints text without pasting. |

## 8. File Structure

```text
.
├── model/                 # Local SenseVoiceSmall model
├── sensevoice_ime.py      # Main push-to-talk voice input program
├── config.json            # Model path, hotkeys, recording, paste, and silence settings
├── phrases.json           # Common phrase replacement rules
├── requirements.txt       # Python dependencies
├── run.bat                # One-click startup script
├── test_model.bat         # One-click model verification script
├── setup.bat              # Optional: create venv and install dependencies
├── README.md              # User and developer documentation (English)
├── README_CN.md           # User and developer documentation (Chinese)
├── DEV_LOG.md             # Iteration history and design notes (English)
└── DEV_LOG_CN.md          # Iteration history and design notes (Chinese)
```

## 9. FAQ

Q: Is text pasted immediately when I release the hotkey?
A: Release stops recording immediately. The text appears after model inference finishes. The console should show `[recording] stopped`, then `[transcribe] working...`, then `[paste] sent to active input`.

Q: Why does the hotkey no longer open Codex / VS Code terminal?
A: Starting from v0.3.2 the hotkey is **suppressed** before reaching the focused app. This prevents app-level shortcuts from conflicting with push-to-talk. If you prefer the old behavior, change `push_to_talk_hotkey` in `config.json` to a less common combo.

Q: Ctrl+Backtick does not work in Codex or another app. Why?
A: Some applications reserve Ctrl+Backtick for their own terminal or command panel. Even with suppression, the global listener may not receive the event if the app hooks the keyboard at a lower level. Change `push_to_talk_hotkey` in `config.json`, for example to `ctrl+shift+space`, then restart `run.bat`.

Q: The cursor disappears or the target app loses focus.
A: The target app may be reacting to the same hotkey. Use a less-conflicting hotkey and click the target input box again before recording.

Q: The program prints `[skip] audio too quiet`.
A: The RMS volume was below `min_rms`. Lower `min_rms` in `config.json` if your microphone is quiet, or speak closer to the microphone.

Q: Random words appear from silence.
A: Raise `min_rms` in `config.json` so quiet background noise is skipped.

Q: The text is recognized but not pasted.
A: Some apps block synthetic paste. Try clicking the input box again, run the console as administrator, or manually paste from the clipboard.

Q: Which microphone is used?
A: `sounddevice` uses the system default input device. Run `python sensevoice_ime.py --list-devices` to inspect available devices.

## 10. Roadmap

Current status: MVP / prototype. It is usable, but still intentionally small and script-based.

Near term:

- Add a small tray icon so the console window is not required.
- Add a hotkey conflict checker that warns when a chosen shortcut is likely to be captured by common apps.
- Add optional sound cues for recording start and stop.

Mid term:

- Add a simple settings window for model path, microphone, hotkey, and phrase replacements.
- Add better VAD so silence and short pauses are handled more naturally.
- Add per-application hotkey profiles for apps like Codex that already use Ctrl+Backtick.

Long term:

- Evolve from an MVP script into a local voice input companion for writing, coding, notes, and chat.
- Keep the core local-first: audio stays on the machine and users can swap ASR models.

How to contribute:

- Open issues for app-specific hotkey conflicts.
- Add phrase replacement examples for technical terms.
- Improve paste behavior for apps that block synthetic `Ctrl+V`.

## 11. Changelog

### 0.3.2

- Hotkey is now **suppressed** so focused applications (e.g. VS Code, Codex) do not intercept it.
- Added `min_record_seconds` and `max_record_seconds` config options.
- Added `restore_clipboard` and `append_space` config options.
- Fixed default `push_to_talk_hotkey` back to `ctrl+\`` in `config.json`.

### 0.3.1

- Added hotkey conflict documentation and FAQ.
- Improved paste reliability notes.

### 0.3.0

- Replaced toggle recording with push-to-talk.
- Default hotkey is Ctrl+Backtick.
- Added lower-level press/release listening for more reliable stop-on-release behavior.

### 0.2.0

- Added local SenseVoiceSmall model inference.
- Added microphone recording and temporary WAV generation.
- Added phrase replacement rules.
- Added quiet audio skip with `min_rms`.

### 0.1.0

- Created standalone Python MVP inside the OpenWhispr checkout.
- Added `run.bat`, `test_model.bat`, `config.json`, and `requirements.txt`.
