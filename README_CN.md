# SenseVoice IME MVP

一款极简的 Windows 按键说话语音输入工具，使用本地 SenseVoiceSmall 模型将语音转写为文字，并自动粘贴到当前输入框。

## 1. 一句话定位

SenseVoice IME MVP 将本地 `iic/SenseVoiceSmall` 模型变成一个轻量级语音输入法：按住热键 → 说话 → 松开 → 识别出的文字自动出现在光标处。

## 2. 解决的痛点

在使用本工具之前：

- 语音识别需要打开专门的转写应用，复制文字，再手动粘贴。
- 本地的 SenseVoice 模型已经下载，却和日常打字工作流脱节。
- 听写工具往往藏在庞大的桌面应用或云账号背后，热键行为不透明。
- 产品名、项目名、工具名等自定义词汇容易被误识别。

现在：

- 按住一个热键开始录音，松开后自动转写并粘贴。
- 模型完全在本地 `model/SenseVoiceSmall` 运行。
- 通过简单的 JSON 文件控制常用词替换。
- 过安静的录音会被跳过，减少误触发。
- 热键会被**拦截**，因此焦点应用（如 VS Code、Codex、浏览器）不会收到该快捷键。

适合谁用：

- 重度键盘用户，想在 Obsidian、浏览器表单、聊天框和编辑器里快速语音输入。
- 本地 AI 用户，已经下载了 SenseVoiceSmall，想把它真正用在日常输入里。
- 开发者，想在构建完整输入法或 Electron UI 之前，先实验一个小而可修改的听写流程。

## 3. 核心功能

| 功能 | 解决的问题 |
| --- | --- |
| 按键说话录音 | 避免全天候监听，让听写更有意图性。 |
| 松开即转写 | 用户松开热键时立即停止录音，然后开始识别。 |
| 本地 SenseVoiceSmall 推理 | 使用已有的本地模型，音频不发送到云端。 |
| 剪贴板粘贴输出 | 将识别结果复制到剪贴板并发送 `Ctrl+V`，兼容大多数应用。 |
| 常用词替换 | 修正反复出现的词汇，如 `SenseVoice`、`OpenWhispr`、`Markdown` 及自定义项目术语。 |
| 静音跳过 | 防止低音量背景噪音被误识别为文字并粘贴。 |
| 热键拦截 | 防止 VS Code、Codex 等应用抢先响应 push-to-talk 快捷键。 |
| 可配置热键 | 让用户避开与已有快捷键（如 grave 键）的冲突。 |

## 4. 安装

### 前置条件

- Windows 桌面环境。
- 已安装 Python 3.11。
- 本地模型文件夹存在：

```text
model/SenseVoiceSmall
```

- 已安装 Python 依赖：

```bat
python -m pip install -r requirements.txt
```

或者运行辅助脚本：

```bat
setup.bat
```

当前测试环境已安装的依赖：

```text
funasr, modelscope, torch, sounddevice, soundfile, keyboard, pyperclip, numpy
```

### 配置模型路径

打开 `config.json`，确认：

```json
"model_path": "model/SenseVoiceSmall"
```

### 配置按键说话热键

默认值：

```json
"push_to_talk_hotkey": "`"
```

程序内部将反引号键映射为 `grave`，因为 Python `keyboard` 包在 Windows 上把该键命名为 `grave`。

## 5. 使用方法

### 场景 1：向任意文本框听写输入

适用时机：你想在 Obsidian、浏览器、聊天框或其他编辑器里输入文字，不想打字。

1. 运行 `run.bat`。
2. 等待控制台打印 `[model] ready` 和 `[ready]`。
3. 点击目标输入框，确保光标在其中。
4. 按住 <kbd>`</kbd>（反引号 / grave 键）。
5. 说话。
6. 松开 <kbd>`</kbd>。
7. 等待 `[transcribe] working...` 和 `[paste] sent to active input`。

### 场景 2：添加常用词

适用时机：SenseVoice 反复把某个项目名或技术术语写错。

1. 打开 `phrases.json`，或在程序运行时按 `Ctrl+Alt+P`。
2. 添加一条替换规则：

```json
{ "spoken": "sense voice", "replace": "SenseVoice" }
```

3. 保存文件。
4. 按 `Ctrl+Alt+R` 即可重新加载词库，无需重启程序。

### 场景 3：不录音测试模型

适用时机：你想确认本地模型能正常加载。

```bat
python sensevoice_ime.py --test-model
```

期望输出包含：

```text
[model] ready
[test] ...
```

### 场景 4：只录音不粘贴

适用时机：你想在正式使用前先调试麦克风输入。

```bat
python sensevoice_ime.py --once 3 --no-paste
```

## 6. 配置参考（`config.json`）

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `model_path` | `model/SenseVoiceSmall` | 本地 SenseVoiceSmall 模型路径。 |
| `language` | `auto` | 识别语言。`auto` 让模型自动判断。 |
| `device` | `auto` | 推理设备。`auto` 优先使用 `cuda:0`，否则回退到 `cpu`。 |
| `sample_rate` | `16000` | 麦克风采样率（Hz）。 |
| `channels` | `1` | 录音通道数。 |
| `push_to_talk_hotkey` | `` ` `` | 按住此热键开始录音。 |
| `reload_phrases_hotkey` | `ctrl+alt+r` | 不重启程序重新加载 `phrases.json`。 |
| `open_phrases_hotkey` | `ctrl+alt+p` | 用默认编辑器打开 `phrases.json`。 |
| `paste_after_transcribe` | `true` | 识别完成后是否自动粘贴结果。 |
| `append_space` | `false` | 是否在识别文本末尾追加一个空格。 |
| `restore_clipboard` | `false` | 粘贴后是否恢复之前的剪贴板内容。 |
| `min_record_seconds` | `0.3` | 最短录音时长；短于该时长的录音会被丢弃。 |
| `max_record_seconds` | `60` | 最长录音时长，超过后强制停止。 |
| `min_rms` | `0.003` | RMS 音量阈值；更安静的音频会被跳过，避免误识别。 |

## 7. 技术栈 / 工具链 / 依赖

| 层级 | 技术 |
| --- | --- |
| 语言 | Python 3.11 |
| ASR 模型 | 本地 `iic/SenseVoiceSmall` 模型 |
| ASR 运行时 | FunASR `AutoModel` |
| 模型来源 | ModelScope 本地缓存 |
| 音频采集 | `sounddevice` |
| 音频文件输出 | `soundfile` 临时 WAV 文件 |
| 热键 | Python `keyboard` 包 |
| 粘贴桥梁 | `pyperclip` + 模拟 `Ctrl+V` |
| 数值处理 | `numpy` RMS 计算 |

| 工具 | 用途 |
| --- | --- |
| `run.bat` | 启动按键说话听写循环。 |
| `test_model.bat` | 运行本地模型验证。 |
| `setup.bat` | 创建虚拟环境并安装依赖。 |
| `--list-devices` | 列出可用麦克风设备。 |
| `--once N --no-paste` | 录音 N 秒并打印文字，不粘贴。 |

## 8. 文件结构

```text
.
├── model/                 # 本地 SenseVoiceSmall 模型
├── sensevoice_ime.py      # 主程序：按键说话语音输入
├── config.json            # 模型路径、热键、录音、粘贴及静音设置
├── phrases.json           # 常用词替换规则
├── requirements.txt       # Python 依赖
├── run.bat                # 一键启动脚本
├── test_model.bat         # 一键模型验证脚本
├── setup.bat              # 可选：创建虚拟环境并安装依赖
├── README.md              # 用户与开发者文档（英文）
├── README_CN.md           # 用户与开发者文档（中文）
├── DEV_LOG.md             # 迭代历史与设计笔记（英文）
└── DEV_LOG_CN.md          # 迭代历史与设计笔记（中文）
```

## 9. 常见问题

Q：松开热键后文字会立即粘贴吗？
A：松开会立即停止录音。文字在模型推理完成后才会出现。控制台会依次显示 `[recording] stopped`、`[transcribe] working...`、`[paste] sent to active input`。

Q：为什么热键不再触发其他应用了？
A：从 v0.3.2 开始，热键会在到达焦点应用之前被**拦截**。这可以防止应用级快捷键与按键说话冲突。如果你希望恢复旧行为，可以在 `config.json` 中换一个更不常用的组合键。

Q：反引号键在某些应用里无法触发录音，为什么？
A：某些应用可能会在更低的键盘钩子层面占用 grave 键。如果拦截不够，你可以在 `config.json` 中修改 `push_to_talk_hotkey`，例如改成 `ctrl+shift+space`，然后重启 `run.bat`。

Q：光标消失或目标应用失去焦点。
A：目标应用可能在响应同一个热键。请换一个冲突更少的热键，并在录音前重新点击目标输入框。

Q：程序打印 `[skip] audio too quiet`。
A：RMS 音量低于 `min_rms`。如果你的麦克风音量较小，可以在 `config.json` 中降低 `min_rms`，或离麦克风更近一些说话。

Q：静音时随机出现文字。
A：在 `config.json` 中提高 `min_rms`，让安静的背景噪音被跳过。

Q：文字已识别但没有粘贴。
A：某些应用会阻止模拟粘贴。请尝试重新点击输入框、以管理员身份运行控制台，或从剪贴板手动粘贴。

Q：使用的是哪个麦克风？
A：`sounddevice` 使用系统默认输入设备。运行 `python sensevoice_ime.py --list-devices` 查看可用设备。

## 10. 路线图

当前状态：MVP / 原型。可用，但有意保持小而脚本化的形态。

近期：

- 添加一个小托盘图标，让控制台窗口不必一直开着。
- 添加热键冲突检测器，当所选快捷键可能被常见应用截获时发出警告。
- 添加可选的录音开始/停止音效提示。

中期：

- 添加一个简单的设置窗口，用于配置模型路径、麦克风、热键和常用词替换。
- 添加更好的 VAD（语音活动检测），让静音和短暂停顿处理得更自然。
- 添加按应用区分的热键配置方案，例如针对已使用 grave 键的应用。

远期：

- 从 MVP 脚本演进成本地语音输入伴侣，覆盖写作、编程、笔记和聊天场景。
- 坚持本地优先核心原则：音频不离开本机，用户可自由更换 ASR 模型。

如何贡献：

- 为特定应用的热键冲突提交 Issue。
- 为技术术语添加常用词替换示例。
- 改进在阻止模拟 `Ctrl+V` 的应用中的粘贴行为。

## 11. 更新日志

### 0.3.2

- 热键现在会被**拦截**，焦点应用不会再抢先响应。
- 新增 `min_record_seconds` 和 `max_record_seconds` 配置项。
- 新增 `restore_clipboard` 和 `append_space` 配置项。
- 修复 `config.json` 中默认 `push_to_talk_hotkey` 为 `` ` ``（单 grave 键）。

### 0.3.1

- 新增热键冲突文档与 FAQ。
- 改进粘贴可靠性的说明。

### 0.3.0

- 将开关录音改为按键说话模式。
- 默认热键为反引号（grave 键 `）。
- 新增更低层级的按下/松开监听，让松开即停止更可靠。

### 0.2.0

- 新增本地 SenseVoiceSmall 模型推理。
- 新增麦克风录音与临时 WAV 生成。
- 新增常用词替换规则。
- 新增基于 `min_rms` 的静音跳过。

### 0.1.0

- 在 OpenWhispr 仓库内创建独立的 Python MVP。
- 新增 `run.bat`、`test_model.bat`、`config.json`、`requirements.txt`。
