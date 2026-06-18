# SenseVoice IME

SenseVoice IME 是一个 Windows 本地按住说话输入工具：按住热键录音，用本地 ASR 模型识别语音，可选本地 Qwen 文本优化，然后把结果自动粘贴到当前输入框。

当前版本：`1.5.0`

## 1. 一句话定位

这是一个面向中文/英文混合输入的本地语音输入法 MVP，用按住说话替代键盘输入，并通过热词库、本地 ASR、本地文本优化和 GPU 加速提升技术词、项目名、英文缩写的识别稳定性。

## 2. 解决什么痛点

以前是这样的：

- 说中文夹英文技术词时，`GitHub`、`Claude`、`vibe coding`、项目名经常被识别错。
- 长按录音偶尔会漏掉开头，或者误触松开导致一句话被截断。
- 识别错了以后没有原始记录，后面很难复盘到底是 ASR 错、热词错，还是文本优化错。
- 大模型 ASR 和降噪模型如果跑在 CPU 上会明显卡顿，启动和识别都慢。
- 麦克风声音忽大忽小、偶尔爆音，会影响输入体验。

现在是这样的：

- 启动时可选择 SenseVoiceSmall、Qwen3-ASR-0.6B、Qwen3-ASR-1.7B，不同速度和效果可以现场切换。
- 启动时可选择 ASR 运行设备：`0 = CPU`、`1 = GPU/CUDA`，程序会明确显示当前实际设备。
- Qwen3-ASR 可在 CUDA PyTorch 环境下使用 RTX GPU 加速，避免 1.7B 模型全部压在 CPU 上。
- 原始 ASR 文本会记录到 `raw_transcripts.jsonl`，即使打开文本优化，也能回看“模型优化前到底识别了什么”。
- `phrases.json` 作为热词/纠错库纳入仓库，常见术语可以持续积累。
- 音频链路拆成输入保护、可选降噪、输出整理三段，避免为了听感处理牺牲 ASR 速度。

适合谁用：

- 中文/英文混合工作的开发者：经常口述 `GitHub`、`ChatGPT`、`Python`、`Claude`、项目名和命令。
- 想本地优先处理语音输入的人：ASR、热词、文本优化都可以在本机运行。
- 想持续改进个人识别效果的人：通过原始日志和热词库定期复盘错误样本。

## 3. 核心功能

| 功能 | 解决什么问题 |
| --- | --- |
| 按住说话输入 | 不用切换窗口或点击按钮，按住反引号键说话，松开后自动识别并粘贴。 |
| ASR 模型选择 | 默认 SenseVoiceSmall 保持轻量，也可以切到 Qwen3-ASR-0.6B / 1.7B 追求更好的中文方言和混合语言识别。 |
| ASR CPU/GPU 切换 | 启动时明确选择 CPU 或 GPU，避免不知道模型到底跑在哪里；CUDA 不可用时自动回退 CPU 并提示。 |
| 本地 Qwen 文本优化 | 识别后可选 Qwen3-0.6B / 1.7B 修正同音字、技术词、标点和断句。 |
| 热词库 `phrases.json` | 把高频错词、项目名、英文术语做成确定性替换规则，减少重复修正。 |
| 原始 ASR 日志 | 保存优化前文本，方便后续制作微调样本、更新热词库、判断模型真实错误。 |
| 输入保护 InputGuard | 录音回调里只做 DC offset 去除和 limiter，防止后续数字处理造成更严重削波。 |
| 可选 FRCRN 降噪 | 嘈杂环境可打开单麦 16k 降噪；默认关闭，并采用 lazy load，避免启动变慢。 |
| OutputPolish | 降噪后再做 AGC / compressor / final limiter，减少把底噪提前放大的风险。 |
| 运行中重选文本优化 | 在终端输入 `qqq` 回车，可以重新选择文本优化模型。 |

## 4. 安装方法

### 第一步：进入项目目录

PowerShell 里使用：

```powershell
cd "E:\Projects\ai\sensevoice_ime"
```

注意：PowerShell 不支持 `cd /d E:\...` 这种 CMD 写法。

### 第二步：安装基础依赖

如果已经有 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果是第一次创建环境：

```powershell
.\setup.bat
```

### 第三步：安装 CUDA 版 PyTorch（需要 GPU 加速时）

如果你要让 Qwen3-ASR 跑在 NVIDIA GPU 上，确认终端里显示的是 CUDA 版 PyTorch：

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
```

期望看到类似：

```text
torch 2.11.0+cu128
cuda_available True
NVIDIA GeForce RTX 3080 Ti
```

如果显示 `+cpu` 或 `False`，安装 CUDA 版：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

### 第四步：准备本地模型

必须模型：

```text
model/SenseVoiceSmall
```

可选文本优化模型：

```text
model/千问3-0.6B
model/千问3-1.7B
```

可选 Qwen ASR 模型，默认使用 ModelScope 缓存路径：

```text
C:\Users\15403\.cache\modelscope\hub\models\Qwen\Qwen3-ASR-0___6B
C:\Users\15403\.cache\modelscope\hub\models\Qwen\Qwen3-ASR-1___7B
```

可选降噪模型：

```text
model/FRCRN语音降噪-单麦-16k
```

`model/` 目录不上传 GitHub，避免把大模型权重放进仓库。

## 5. 使用方法

### 推荐：图形界面模式

直接双击：

```text
SenseVoiceIME.exe
```

这是桌面程序入口，会打开原生 UI，并支持录音时的置顶悬浮窗。

如果要重新生成 EXE，运行：

```powershell
.\build_launcher_exe.bat
```

也可以用批处理启动同一个桌面 UI：

双击运行：

```powershell
.\run_ui.bat
```

程序会打开本地控制台：

```text
http://127.0.0.1:8765/?connect=1
```

在“设置”页可以直接点击切换：

- 麦克风增强：开 / 关
- FRCRN 降噪：开 / 关
- ASR 设备：CPU / GPU
- ASR 引擎：SenseVoiceSmall / Qwen3-ASR-0.6B / Qwen3-ASR-1.7B
- 文本优化：关闭 / Qwen3-0.6B / Qwen3-1.7B

正在录音或识别时，模型相关选项会暂时拒绝切换；等状态回到待命后再点即可。

### 场景一：日常快速语音输入

什么时候用：想在任意输入框里快速口述中文、英文技术词或短句。

1. 运行：

```powershell
.\run.bat
```

2. 音频处理选择默认 `1`。
3. 降噪默认选 `0`，只有环境很吵时再选 `1`。
4. ASR device 选 `1` 使用 GPU；如果显示退回 CPU，说明 CUDA PyTorch 没装好。
5. ASR engine 默认 `0` 是 SenseVoiceSmall；想试 Qwen 方言/混合识别时选 `1` 或 `2`。
6. 把光标放到任意输入框。
7. 按住 `` ` `` 说话，松开后等待自动粘贴。

### 场景二：测试 Qwen3-ASR 是否真的用 GPU

什么时候用：刚安装 CUDA PyTorch，想确认 0.6B / 1.7B 是否跑在显卡上。

1. 启动程序。
2. `ASR device` 选择 `1`。
3. `ASR engine` 选择 `1` 或 `2`。
4. 观察终端输出：

```text
[model] device: cuda:0
```

如果看到：

```text
[device] GPU selected, but current PyTorch cannot see CUDA; falling back to CPU.
[model] device: cpu
```

说明当前虚拟环境仍是 CPU 版 PyTorch。

### 场景三：复盘识别错误并更新热词

什么时候用：发现 `GitHub`、项目名、英文缩写被反复识别错。

1. 打开：

```text
raw_transcripts.jsonl
```

2. 查看 `raw_text` 和 `final_text` 的差异。
3. 把稳定、确定的错词修正写入：

```text
phrases.json
```

4. 程序运行中按 `ctrl+alt+r` 重新加载热词。

### 场景四：运行中切换文本优化模型

什么时候用：想在不重启程序的情况下，从关闭优化切到 Qwen3-0.6B 或 Qwen3-1.7B。

1. 在运行程序的终端输入：

```text
qqq
```

2. 回车。
3. 重新选择：

```text
0 = off
1 = Qwen3-0.6B
2 = Qwen3-1.7B
```

## 6. 技术栈 / 工具链 / 依赖库

| 层级 | 技术 | 用途 |
| --- | --- | --- |
| 语言 | Python 3.11 | 主程序、音频处理、模型调用。 |
| ASR | FunASR + SenseVoiceSmall | 默认轻量本地语音识别。 |
| ASR | qwen-asr + Transformers | 可选 Qwen3-ASR-0.6B / 1.7B。 |
| 推理 | PyTorch CPU / CUDA | CPU 兼容运行，CUDA 用于 NVIDIA GPU 加速。 |
| 音频录制 | sounddevice | 低延迟麦克风输入。 |
| 音频文件 | soundfile | 临时 WAV 读写。 |
| 热键 | keyboard | 全局按住说话、快捷键注册。 |
| 剪贴板 | pyperclip | 自动粘贴识别结果。 |
| 文本优化 | Transformers + 本地 Qwen3 | 修正 ASR 后文本。 |
| 降噪 | ModelScope FRCRN pipeline | 可选单麦 16k 降噪。 |
| 配置 | JSON | `config.json`、`phrases.json`、`raw_transcripts.jsonl`。 |

主要依赖见 `requirements.txt`。

## 7. 文件结构

```text
sensevoice_ime/
├── sensevoice_ime.py          # 主程序：启动流程、ASR、热键、粘贴、日志
├── config.json                # 本地配置：模型路径、设备选择、音频参数、热键
├── phrases.json               # 热词/错词修正规则，已纳入仓库
├── requirements.txt           # Python 依赖
├── run.bat                    # 日常启动入口
├── setup.bat                  # 环境初始化脚本
├── test_model.bat             # 模型测试入口
├── tools/
│   ├── audio_processor.py     # InputGuard / OutputPolish 音频处理
│   ├── noise_suppressor.py    # FRCRN 降噪封装，lazy load
│   └── __init__.py
├── sounds/                    # 开始/停止录音提示音
├── model/                     # 本地模型目录，不上传 GitHub
├── raw_transcripts.jsonl      # 私人原始识别日志，不上传 GitHub
├── README.md                  # 项目说明
└── DEV_LOG.md                 # 开发日志和设计决策
```

## 8. 常见问题

Q: 为什么我选择 GPU，最后还是显示 CPU？

A: 说明当前 `.venv` 里的 PyTorch 是 CPU 版，或者 CUDA 不可见。先运行 GPU 检测命令，确认 `torch.cuda.is_available()` 是 `True`。如果不是，重新安装 CUDA 版 PyTorch。

Q: 看到 `[model] device: cuda:0` 是不是就说明用了 GPU？

A: 是。`cuda:0` 表示模型已经加载到第一张 NVIDIA GPU 上。

Q: FRCRN 降噪为什么默认关闭？

A: 降噪模型加载慢，而且安静环境下不一定提升 ASR。现在它默认关闭，并且 lazy load，只有你选择开启并开始处理音频时才加载。

Q: 为什么不把 AGC / 压缩器放在降噪前？

A: 降噪模型更喜欢自然动态范围的输入。提前 AGC 会把底噪一起拉高，压缩器也会抹平语音和噪声差异，所以当前链路是 `InputGuard -> FRCRN -> OutputPolish -> ASR`。

Q: `raw_transcripts.jsonl` 在 GitHub 上看不到？

A: 这是私人语音识别日志，包含你的口述内容，所以被 git ignore。它只保存在本地。

Q: PowerShell 里 `cd /d E:\...` 报错怎么办？

A: PowerShell 用 `cd "E:\Projects\ai\sensevoice_ime"`，`/d` 是 CMD 的写法。

Q: 安装 CUDA PyTorch 后出现 `~orch`、`~umpy` 临时目录警告怎么办？

A: 通常不影响运行。确认程序能跑 GPU 后，可以再清理 `.venv\Lib\site-packages` 下这些 `~` 开头的临时残留。

Q: 那句 `generation flags are not valid and may be ignored: ['temperature']` 是错误吗？

A: 不是致命错误，是 Transformers 的提醒，不影响 Qwen3-ASR 正常识别。

## 9. 未来开发路线图

当前状态：稳定可用的本地语音输入 MVP，GPU 加速和多 ASR 后端已经打通。

近期：

- 轻量静音裁剪 —— 对讲话很慢、中间空白很多的录音，在送入 ASR 前删除长静音，减少 Qwen ASR 推理时间。
- ASR 性能日志 —— 记录每次识别的模型、设备、音频时长、推理耗时，方便比较 SenseVoiceSmall / Qwen3-ASR-0.6B / 1.7B。
- GPU 环境自检 —— 启动时更明确地区分“选择了 GPU”和“实际跑在 GPU”。

中期：

- 样本复盘工具 —— 从 `raw_transcripts.jsonl` 生成可标注的纠错样本，用于热词更新或后续微调。
- 领域语言画像导入 —— 从个人笔记、网站、常用术语生成一份轻量 profile，作为文本优化上下文或热词来源。
- 更细的音频策略配置 —— 针对安静房间、键盘噪声、远场麦克风分别保存参数。

长期愿景：

- 成为一个本地优先、可持续学习个人语言习惯的中文/英文混合语音输入工作台。
- 差异化定位不是“通用语音助手”，而是“开发者和知识工作者自己的本地输入层”。

如何参与：

- 有稳定复现的误识别，优先提交原始 ASR 文本、期望文本和场景说明。
- 有新的模型后端，先做独立 engine 封装，再接入启动选择菜单。

## 10. 更新日志

v1.5.0 (2026-06-12) Added Ctrl+Alt+Win+M system-audio push-to-talk recording and changed the recommended hotkeys to Ctrl+Alt+Win+L / Ctrl+Alt+Win+M; added automatic Loopback / Stereo Mix / Monitor input detection; added system_audio_hotkey, system_audio_device_index, system_audio_min_rms, and related config; system-audio stream opens only while the hotkey is held to avoid permanent device occupation.

v1.4.0 (2026-06-12) ✅ 新增 ASR CPU/GPU 启动选择，默认 GPU/CUDA 🔧 修复选择 GPU 但 PyTorch 不可见时无提示的问题 ⚡ 优化 FRCRN 降噪为 lazy load，避免启动阶段强制加载慢模型 ⚡ 完成 CUDA PyTorch 环境验证，Qwen3-ASR 可显示并运行在 `cuda:0` 📋 更新 README / DEV_LOG 为产品、技术、受众三维结构

v1.3.0 (2026-06-12) ✅ 新增 ASR 引擎选择：SenseVoiceSmall / Qwen3-ASR-0.6B / Qwen3-ASR-1.7B ✅ 新增 Qwen3-ASR 本地 ModelScope 缓存路径配置 ✅ 原始日志增加 `asr_engine` 字段，便于比较模型效果

v1.2.0 (2026-06-12) ✅ 新增 InputGuard / OutputPolish 分层音频处理 ✅ 新增可选 FRCRN 单麦 16k 降噪 🔄 统一音频链路为 `麦克风 -> InputGuard -> FRCRN -> OutputPolish -> ASR` ⚡ 避免在降噪前做 AGC / 压缩导致底噪被放大

v1.1.0 (2026-06-11) ✅ 新增原始 ASR 日志 `raw_transcripts.jsonl` ✅ 新增 `phrases.json` 热词库并纳入仓库 🔧 修复 `duration` / `rms` 日志字段缺失 🔧 修复 `torchaudio` 缺失导致 FunASR 启动失败 ⚡ 优化预录音和热键释放防抖，减少开头截断和随机停止

v1.0.0 (2026-06-11) 🚀 初始可用版本：SenseVoiceSmall 本地识别、按住说话、自动粘贴 ✅ 新增 Qwen3-0.6B / 1.7B 文本优化选择 ✅ 新增 `qqq` 运行中重选文本优化模型 📋 建立配置、热词、运行脚本和基础文档
