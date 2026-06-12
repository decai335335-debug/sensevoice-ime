# SenseVoice IME DEV_LOG

## 1. 项目起源

SenseVoice IME 起源于一个很具体的需求：在 Windows 上用一个尽量轻的本地工具，把中文/英文混合口述快速变成当前输入框里的文本。

原始目标不是做完整输入法框架，而是先做一个能日常使用的 MVP：按住一个热键录音，松开后本地 ASR 识别，然后自动粘贴。随着实际使用，需求逐步扩展到热词纠错、本地 Qwen 文本优化、原始日志复盘、音频链路处理、可选降噪、Qwen3-ASR 方言识别，以及 GPU 加速。

这个项目的核心判断是：语音输入的真正难点不只是“模型识别”，而是个人语言习惯、技术词、混合语言、麦克风质量、运行速度和可复盘性一起决定最终体验。

## 2. 迭代时间线

### v1.4.0 - GPU 设备选择与启动速度优化

日期：2026-06-12

- 新增 ASR device 启动选择：`0 = CPU`、`1 = GPU / CUDA`。
- 默认 ASR device 设为 GPU，适配 RTX 3080 Ti 等 NVIDIA 显卡场景。
- 当用户选择 GPU 但当前 PyTorch 看不到 CUDA 时，明确提示并自动回退 CPU。
- 安装并验证 CUDA 版 PyTorch：`torch 2.11.0+cu128`，`torch.cuda.is_available() = True`，设备为 `NVIDIA GeForce RTX 3080 Ti`。
- 将 FRCRN 降噪从启动预加载改为 lazy load，避免开启程序时被慢模型阻塞。
- 更新 README 和 DEV_LOG 为产品、技术、受众三维结构。

### v1.3.0 - 可选 ASR 引擎

日期：2026-06-12

- 新增启动 ASR 引擎选择：`0` SenseVoiceSmall、`1` Qwen3-ASR-0.6B、`2` Qwen3-ASR-1.7B。
- 新增 `QwenAsrEngine`，通过 `qwen-asr` 和 Transformers 调用本地 Qwen3-ASR 模型。
- 新增 Qwen3-ASR 配置项：模型路径、语言、批量大小、最大生成 token。
- 原始日志新增 `asr_engine` 字段，便于比较不同 ASR 后端效果。

### v1.2.0 - 音频链路分层与可选 FRCRN 降噪

日期：2026-06-12

- 将音频处理拆成 `InputGuard -> optional FRCRN denoise -> OutputPolish -> ASR`。
- `InputGuard` 放在录音回调中，只做 DC offset 去除和 limiter。
- `OutputPolish` 放在降噪之后，处理 AGC / compressor / final limiter。
- 新增 `tools/audio_processor.py` 和 `tools/noise_suppressor.py`。
- 新增 FRCRN 单麦 16k 降噪开关，默认关闭。
- 原始日志增加 RMS、peak、处理增益、降噪状态等音频元数据。

### v1.1.0 - 热词库、原始日志与录音稳定性

日期：2026-06-11

- 新增 `raw_transcripts.jsonl`，记录优化前 ASR 结果和最终输出。
- 新增 `pre_roll_seconds`，减少开头被截断。
- 新增 `restrict_output_to_zh_en`，降低自动语言检测误出韩文/日文字符的概率。
- 新增 `hotkey_release_debounce_seconds`，减少长按时随机停止。
- 扩展 `phrases.json`，把 GitHub、Claude、Python、vibe coding 等常用词加入热词修正规则。
- 修复日志字段、依赖缺失、热词替换顺序和重复替换问题。

### v1.0.0 - 本地 Qwen 文本优化版本

日期：2026-06-11

- 新增 `TextOptimizer`：`0` 关闭、`1` Qwen3-0.6B、`2` Qwen3-1.7B。
- 新增运行中输入 `qqq` 重新选择文本优化模型。
- 新增 Transformers 依赖和本地 Qwen 模型路径配置。
- 建立基础 README、配置说明和本地模型工作流。

### v0.x - MVP 阶段

- 建立独立 Python 脚本、配置文件、热词规则、运行脚本。
- 接入 FunASR / SenseVoiceSmall。
- 完成按住说话、临时 WAV、短音频过滤、短句粘贴、提示音等基础功能。

## 3. 踩坑记录

| 问题 | 根因 | 解决方案 | 涉及版本 |
| --- | --- | --- | --- |
| 选择 GPU 但模型仍显示 CPU | `.venv` 里安装的是 CPU 版 PyTorch，`torch.cuda.is_available()` 为 `False` | 安装 CUDA 版 PyTorch，并在启动时加入 ASR device 显式选择和回退提示 | v1.4.0 |
| FRCRN 开启后启动特别慢 | 降噪模型在 `ImeApp.start()` 阶段预加载，即使还没录音也会加载模型 | 改为 lazy load，只在实际处理音频时加载 | v1.4.0 |
| Qwen3-ASR-1.7B CPU 推理很慢 | 大模型 ASR 权重和推理都压在 CPU 上 | 增加 CUDA 环境验证，确认 `[model] device: cuda:0` 后再使用 1.7B | v1.4.0 |
| 自动语言检测出现韩文/日文字符 | SenseVoice auto 模式在相似音或噪声下可能误判脚本 | 加入中英输出限制和热词修正 | v1.1.0 |
| 长按录音偶尔随机停止 | 热键释放事件抖动或系统层面误触发 | 增加释放防抖 `hotkey_release_debounce_seconds` | v1.1.0 |
| 句首被截断 | 用户按下热键后开始讲话太快，录音流尚未完整覆盖开头 | 增加 `pre_roll_seconds` 预录音缓冲 | v1.1.0 |
| `duration` 未定义导致报错 | 原始日志新增字段时，worker 队列元数据没有同步 | 队列里补齐 `duration`、`rms` 等字段 | v1.1.0 |
| `torchaudio` 缺失 | FunASR 间接依赖没有在环境中安装 | 将 `torchaudio` 写入依赖并重新安装 | v1.1.0 |
| PowerShell `cd /d` 报错 | `/d` 是 CMD 参数，PowerShell 的 `Set-Location` 不接受 | 文档统一改为 `cd "E:\Projects\ai\sensevoice_ime"` | v1.0.0 |
| 中文模型路径在旧文档中乱码 | 旧终端或文件显示编码不一致 | README 使用 UTF-8 中文路径重新写入 | v1.4.0 |

## 4. 设计决策

### 为什么保留 SenseVoiceSmall 作为默认 ASR

SenseVoiceSmall 启动快、资源占用低，适合日常短句输入。Qwen3-ASR-0.6B / 1.7B 在方言和混合语言上更有潜力，但加载和显存压力更大，所以作为可选后端更稳妥。

### 为什么加入 ASR CPU/GPU 开关

原先代码是自动检测 CUDA，有 CUDA 就用 GPU，没有就 CPU。实际排查时，用户很难判断“我选了 GPU”和“模型实际跑在 GPU”是不是同一件事。显式开关可以让启动日志直接暴露问题：如果 PyTorch 是 CPU 版，就立刻提示并回退。

### 为什么 FRCRN 默认关闭并 lazy load

降噪不是所有场景都必要。安静环境下，降噪模型可能增加等待时间，却不一定提升识别。FRCRN 加载慢，所以默认关闭；即使用户选择开启，也只在真正需要处理音频时加载，避免阻塞启动。

### 为什么 InputGuard 放在最前面

Limiter 的任务是防止后续数字处理继续放大峰值，因此必须尽早执行。DC offset 去除也足够轻，适合放在录音回调里。这里不放重模型，也不放慢 AGC，避免影响实时录音稳定性。

### 为什么 AGC / compressor 放在降噪之后

AGC 会把底噪也拉高，compressor 会压缩语音和噪声之间的动态差异。降噪模型需要自然的噪声结构来判断什么是语音、什么是背景，所以 AGC / compressor 放在降噪之后更合理。

### 为什么保留原始 ASR 日志

最终输出可能经过热词库和 Qwen 优化，单看最终文本无法知道 ASR 到底错在哪里。`raw_transcripts.jsonl` 保存优化前文本，是后续热词更新、样本标注、微调数据准备的基础。

## 5. 实际测试数据

| 测试项 | 结果 |
| --- | --- |
| CUDA PyTorch 验证 | `torch 2.11.0+cu128`，`torch.cuda.is_available() = True` |
| GPU 设备 | `NVIDIA GeForce RTX 3080 Ti` |
| Qwen3-ASR-1.7B 设备显示 | `[model] device: cuda:0` |
| Qwen3-ASR-1.7B checkpoint 加载 | 2/2 shards，约 3 秒多完成 |
| 主程序语法检查 | `python -m py_compile sensevoice_ime.py` 通过 |
| FRCRN 启动加载 | v1.4.0 起不再启动预加载，改为 lazy load |
| 原始日志 | `raw_transcripts.jsonl` 本地生成，不上传 GitHub |

## 6. 文件位置

```text
sensevoice_ime/
├── sensevoice_ime.py          # 主程序：启动选择、ASR、热键、粘贴、日志
├── config.json                # 配置：设备、模型、音频、热键、日志
├── phrases.json               # 热词/纠错库，纳入仓库
├── requirements.txt           # Python 依赖
├── run.bat                    # 日常启动入口
├── setup.bat                  # 环境初始化入口
├── test_model.bat             # 模型测试入口
├── tools/
│   ├── audio_processor.py     # InputGuard / OutputPolish
│   ├── noise_suppressor.py    # FRCRN 降噪封装
│   └── __init__.py
├── sounds/                    # 录音开始/停止提示音
├── model/                     # 本地模型，不上传
├── raw_transcripts.jsonl      # 私人原始识别日志，不上传
├── README.md                  # 项目说明
└── DEV_LOG.md                 # 开发日志
```
