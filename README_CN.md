# SenseVoice IME

SenseVoice IME 是一个 Windows 按键说话语音输入工具。按住热键时录音，松开后用本地 SenseVoiceSmall 识别语音，再可选使用本地 Qwen3 模型优化文本，最后把结果粘贴到当前输入框。

当前版本：`1.0.0`

## 主要功能

- 使用本地 `model/SenseVoiceSmall` 做语音识别。
- 默认按住反引号/ grave 键 `` ` `` 录音。
- 识别完成后自动复制到剪贴板并发送 `Ctrl+V`。
- 通过 `phrases.json` 维护常用词和错词替换。
- 识别后可选调用本地文本优化模型：
  - `0`：关闭，保持原来的 SenseVoice 流程。
  - `1`：使用 `Qwen3-0.6B`。
  - `2`：使用 `Qwen3-1.7B`。
- 运行中输入 `qqq` 并回车，可以重新选择 `0/1/2`，不用重启程序。
- 支持开始/停止录音音效。
- 使用 RMS 音量阈值跳过过安静的录音，减少误识别。

## 环境要求

- Windows。
- 推荐 Python 3.11。
- 本地 SenseVoiceSmall 模型目录：

```text
model/SenseVoiceSmall
```

- 可选的本地 Qwen3 模型目录：

```text
model/千问3-0.6B
model/千问3-1.7B
```

`model/` 已经被 `.gitignore` 忽略，不会上传到 GitHub。

## 安装

PowerShell：

```powershell
cd "E:\Projects\ai\sensevoice_ime"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

也可以运行：

```powershell
.\setup.bat
```

## 使用

```powershell
cd "E:\Projects\ai\sensevoice_ime"
.\run.bat
```

启动后会要求选择文本优化模型：

```text
Text optimizer:
  0 = off / keep current behavior
  1 = Qwen3-0.6B
  2 = Qwen3-1.7B
Choose text optimizer [0/1/2, default 0]:
```

然后：

1. 把光标放到任意输入框。
2. 按住 `` ` ``。
3. 说话。
4. 松开按键。
5. 等待识别、优化和粘贴。

按 `Esc` 退出。

## 运行中切换模型

在程序运行的终端里输入：

```text
qqq
```

然后回车。程序会重新显示 `0/1/2` 选择菜单。之后的识别会使用新选择的模式。

## 配置

编辑 `config.json`：

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
  "sound_on_stop": "sounds/stop.wav"
}
```

常用字段：

| 字段 | 说明 |
| --- | --- |
| `model_path` | 本地 SenseVoiceSmall 路径。 |
| `device` | `auto` 会优先使用 CUDA，否则使用 CPU。 |
| `qwen_0_6b_path` | 本地 Qwen3-0.6B 路径。 |
| `qwen_1_7b_path` | 本地 Qwen3-1.7B 路径。 |
| `prompt_text_optimizer_on_start` | 启动时是否询问 `0/1/2`。 |
| `text_optimizer_default` | 默认文本优化模式。 |
| `text_optimizer_max_new_tokens` | 文本优化模型最大输出 token 数。 |
| `push_to_talk_hotkey` | 按住录音的热键。 |
| `reload_phrases_hotkey` | 不重启程序，重新加载 `phrases.json`。 |
| `open_phrases_hotkey` | 打开 `phrases.json`。 |
| `min_rms` | 静音跳过阈值。 |

## 常用词替换

编辑 `phrases.json` 可以先做强规则替换，再交给 Qwen 优化：

```json
[
  { "spoken": "cloud code", "replace": "Claude Code" },
  { "spoken": "chat G", "replace": "ChatGPT" },
  { "spoken": "sense voice", "replace": "SenseVoice" }
]
```

运行中重新加载：

```text
Ctrl+Alt+R
```

运行中打开文件：

```text
Ctrl+Alt+P
```

## Qwen 模型目录

完整的 Qwen 本地模型目录通常需要包含：

```text
config.json
tokenizer.json
generation_config.json
model.safetensors
```

或者分片权重：

```text
model-00001-of-00002.safetensors
model-00002-of-00002.safetensors
model.safetensors.index.json
```

如果选 `1` 或 `2` 时目录不完整，程序会提示缺少哪个文件。

## 开发命令

列出音频设备：

```powershell
.\.venv\Scripts\python.exe .\sensevoice_ime.py --list-devices
```

测试 SenseVoice 示例音频：

```powershell
.\.venv\Scripts\python.exe .\sensevoice_ime.py --test-model
```

录音一次但不粘贴：

```powershell
.\.venv\Scripts\python.exe .\sensevoice_ime.py --once 3 --no-paste
```

语法检查：

```powershell
python -m py_compile sensevoice_ime.py
```

## 文件结构

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
`-- model/              # git 忽略
```

## 已知限制

- 这不是原生 Windows IME 驱动。
- 当前通过剪贴板粘贴文本，某些应用可能阻止或重定向粘贴。
- 控制台窗口需要保持打开。
- Qwen3-1.7B 首次加载会比较慢。
- 运行中切换模型会卸载旧优化器并尝试清理 CUDA 缓存，但实际显存释放仍受 PyTorch 和显卡驱动影响。

## 1.0.0

`1.0.0` 是第一个完整可用版本：本地 SenseVoice 识别、本地 Qwen 文本优化、热词替换、运行中模型切换和基础音频反馈都已经串起来。
