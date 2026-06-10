# SenseVoice IME MVP DEV_LOG

## 1. Project Origin

The original request was to use a locally downloaded SenseVoiceSmall model as a practical voice input method. The user already had the model at:

```text
model/SenseVoiceSmall
```

Instead of modifying the full OpenWhispr Electron application immediately, the first goal was to create a minimum viable version that proves the complete local loop:

1. Capture microphone audio.
2. Run local SenseVoiceSmall inference.
3. Apply common phrase replacements.
4. Paste the recognized text into the current input box.
5. Control the workflow with a keyboard shortcut.

This MVP was originally created in `sensevoice_ime_mvp/` under the OpenWhispr checkout, then extracted to a standalone folder with a local copy of the model.

## 2. Iteration Timeline

### v0.1.0 - Standalone MVP Scaffold

Created a separate folder with:

- `sensevoice_ime.py`
- `config.json`
- `phrases.json`
- `requirements.txt`
- `run.bat`
- `test_model.bat`

Decision: keep the MVP as a Python sidecar first, because integrating SenseVoice into the full Electron app would require changes across main process, renderer state, model management, and packaging.

### v0.2.0 - Local SenseVoice Pipeline

Verified FunASR can load the local model with:

```python
AutoModel(model="model/SenseVoiceSmall", trust_remote_code=False)
```

The bundled `example/zh.mp3` test successfully produced:

```text
??????9???????
```

Added:

- fixed-duration test command
- model test command
- microphone device listing
- phrase replacement JSON
- automatic clipboard paste

### v0.2.1 - Quiet Audio Guard

A 1-second quiet recording produced a false recognition (`Yeah.`). Added RMS measurement and `min_rms` so recordings below the threshold are skipped before inference/paste.

Default:

```json
"min_rms": 0.003
```

### v0.3.0 - Push-To-Talk Hotkey

The user wanted Backtick (grave key) as a hold-to-record shortcut:

- Press and hold: start recording.
- Release: stop recording.
- Then transcribe and paste.

Initial implementation used `keyboard.add_hotkey(... trigger_on_release=True)`, but combo release behavior can be unreliable. The implementation was changed to lower-level listeners:

- listen for `grave` key press
- verify `ctrl` is currently pressed
- start recording
- stop when either `grave` or `ctrl` is released

The user-facing config:

```json
"push_to_talk_hotkey": "`"
```

Internally, backtick is normalized to `grave` for the Python `keyboard` package.

### v0.3.1 - Hotkey Conflict Documentation

Observed that some apps may capture the grave key at a low level. Added FAQ guidance explaining that app-level shortcuts can prevent the global listener from receiving the event, and users can change `push_to_talk_hotkey` in `config.json`.

### v0.3.3 - Sound Cues for Push-To-Talk

Added short beep tones using the existing `sounddevice` + `numpy` stack so users get immediate audio feedback:

- **Start tone**: 880 Hz, 0.08 s (higher, short)
- **Stop tone**: 440 Hz, 0.12 s (lower, slightly longer)

Both are non-blocking via `sd.play(..., blocking=False)` so they do not delay the recording or transcription pipeline. Controlled by `sound_on_start` and `sound_on_stop` in `config.json`.

### v0.3.2 - Hotkey Suppression & Config Hardening

Even with push-to-talk, focused apps could still intercept the grave key because the global hotkey listener does not block the event by default. Added `suppress=True` to `keyboard.add_hotkey` so the key is consumed before the active app sees it.

Also hardened `config.json` defaults:

- `min_record_seconds`: 0.3 (avoids accidental triggers from quick taps)
- `max_record_seconds`: 60 (safety cap to avoid runaway recordings)
- `restore_clipboard`: false (opt-in to avoid surprising clipboard loss)
- `append_space`: false (opt-in)

Fixed `config.json` default `push_to_talk_hotkey` to `` ` `` (single grave key).

## 3. Pitfalls

| Problem | Root Cause | Solution | Version |
| --- | --- | --- | --- |
| Full OpenWhispr integration is too large for an MVP | Electron app has many existing model, recording, and UI paths | Build standalone Python sidecar first | v0.1.0 |
| Local model might require remote code | SenseVoice examples often use `trust_remote_code=True` | Verified local FunASR integrated path works with `trust_remote_code=False` | v0.2.0 |
| Quiet recordings generated false text | ASR can hallucinate short noise or silence | Added RMS threshold and skip logic | v0.2.1 |
| ctrl+backtick cannot be parsed directly | Python `keyboard` package treats backtick specially in hotkey strings | Normalize backtick to `grave` | v0.3.0 |
| Release event was not reliable enough | Combo hotkey release handling can be inconsistent | Use `on_press_key` and `on_release_key` for the trigger key and modifiers | v0.3.0 |
| Some apps capture the grave key | App-level shortcuts can run before the global listener | Document conflict and support changing `push_to_talk_hotkey` | v0.3.1 |
| Some apps do not accept synthetic paste | App security or focus state blocks `Ctrl+V` | Keep recognized text on clipboard and document administrator/focus workaround | v0.3.1 |
| Missing audio feedback for recording state | Users cannot tell when recording actually starts or stops | Generate non-blocking sine-wave beeps with `sounddevice` | v0.3.3 |
| Hotkey still reaches focused app | `keyboard` default forwards the combo to the active window | Add `suppress=True` so the event is intercepted | v0.3.2 |
| Default hotkey drifted to just backtick | Local testing changed `config.json` without updating docs | Restore default to `ctrl+\`` and document it clearly | v0.3.2 |

## 4. Design Decisions

### Why A Python Sidecar Instead Of Editing OpenWhispr Directly?

| Option | Pros | Cons | Decision |
| --- | --- | --- | --- |
| Modify full OpenWhispr Electron app | Native product integration | Larger blast radius, more build/package work | Not for MVP |
| Python sidecar | Fast to build, direct access to FunASR, easy to test | Console-based, not polished | Chosen |
| Full Windows IME driver | Best native input experience | Very high complexity | Future only |

### Why Clipboard Paste?

A real IME requires OS-level integration. For an MVP, clipboard paste works in most text boxes and avoids Windows IME driver complexity. It also keeps the recognized result visible in the clipboard if paste fails.

### Why Push-To-Talk?

Push-to-talk avoids always-on listening and gives the user direct control. It also reduces accidental recording and is easier to reason about than automatic VAD in the first version.

### Why Phrase Replacement JSON?

A simple JSON list is enough to fix common misrecognitions without building a settings UI. It is transparent, editable, and reloadable at runtime.

### Why Suppress The Hotkey?

Without suppression, focused apps that already bind the same shortcut (e.g. VS Code `Ctrl+\`` for integrated terminal) will act on it before or alongside our global listener. This causes the terminal to open while the user only wanted to dictate. `suppress=True` in the `keyboard` package prevents this by consuming the event.

## 5. Actual Test Data

| Test | Result |
| --- | --- |
| FunASR dependency installed | Success |
| Local SenseVoiceSmall model path exists | Success |
| Model loads on `cuda:0` | Success |
| `--test-model` on `example/zh.mp3` | Success, recognized Chinese sentence |
| `--list-devices` | Success, detected default input device |
| `--once 1 --no-paste` quiet recording | Skipped after RMS threshold was added |
| ctrl+backtick parsing | Fails directly in `keyboard`, succeeds after normalization to `ctrl+grave` |
| Push-to-talk parser | ctrl+backtick maps to modifiers `['ctrl']` and trigger `grave` |
| Hotkey suppression in VS Code | Success; terminal no longer opens when `Ctrl+\`` is held for dictation |
| `min_record_seconds` guard | Quick taps are discarded instead of triggering false recognition |

## 6. File Location

```text
.
├── model/
├── sensevoice_ime.py
├── config.json
├── phrases.json
├── requirements.txt
├── run.bat
├── test_model.bat
├── setup.bat
├── README.md
├── README_CN.md
├── DEV_LOG.md
└── DEV_LOG_CN.md
```

## Current Known Limitations

- It is not a native Windows IME driver.
- It uses clipboard paste, so some apps may block or redirect paste.
- Hotkeys can conflict with apps that reserve the grave key at a lower level.
- The console window must remain open.
- Microphone selection is currently system-default only.
