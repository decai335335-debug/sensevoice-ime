# SenseVoice IME 开发日志

## 1.1.0 - 热词库、原始日志与录音稳定性版本

日期：2026-06-11

### 新增

- 新增 原始识别日志 `raw_transcripts.jsonl`，记录 Qwen 优化前的 `asr_raw`、`asr_sanitized`、`asr_after_phrases` 和最终输出。
- 新增 预录音缓冲 `pre_roll_seconds`，默认 0.5 秒，减少按下热键后立即说话导致开头被截断。
- 新增 输出语言限制 `restrict_output_to_zh_en`，过滤 SenseVoice 自动语言检测误产生的韩文/日文假字符。
- 新增 热键释放防抖 `hotkey_release_debounce_seconds`，减少长按录音时随机停止。
- 新增 GitHub 强纠错热词和大规模个人技术热词库，`phrases.json` 扩展到 417 条并随仓库上传。

### 修复

- 修复 `duration` / `rms` 未传入后台 worker，导致识别完成后写日志时报错的问题。
- 修复 `run.bat` / `setup.bat` 查找 `venv` 而不是 `.venv` 的问题。
- 修复缺少 `torchaudio` 导致 FunASR 无法导入的问题。
- 修复短热词优先匹配破坏长热词的问题，改为长词优先。
- 修复英文热词在已替换结果内部重复命中，避免 `GitHub` 变成 `GitGitHub`。

### 说明

- `phrases.json` 是项目热词库，继续作为仓库文件上传。
- `raw_transcripts.jsonl` 是个人识别日志，继续被 `.gitignore` 忽略。

## 1.0.0 - 本地 LLM 文本优化版本

日期：2026-06-11

这个版本把 MVP 串成了完整的本地语音输入流程：SenseVoice 负责语音识别，`phrases.json` 负责确定性的常用词替换，可选的 Qwen3 模型负责在粘贴前优化识别文本。

### 新增

- 新增 `TextOptimizer`，启动时可选择三种模式：
  - `0`：关闭，保持原来的行为。
  - `1`：使用本地 `Qwen3-0.6B` 优化文本。
  - `2`：使用本地 `Qwen3-1.7B` 优化文本。
- 在 `config.json` 中新增 Qwen 模型路径：
  - `qwen_0_6b_path`
  - `qwen_1_7b_path`
- 新增 `text_optimizer_default`、`prompt_text_optimizer_on_start`、`text_optimizer_max_new_tokens`。
- 新增运行中命令监听。在终端输入 `qqq` 并回车，可以不用重启程序就重新选择模型。
- 切换模型时会卸载旧优化器，并在可用时清理 CUDA 缓存。
- 新增 `transformers` 依赖，用于加载本地 Qwen 模型。
- 扩展 `phrases.json`，支持更多个人技术词汇和错词修正。
- 重写并更新 `README.md` 和 `README_CN.md`，记录 1.0.0 使用方式。

### 修改

- 识别流程变为：

```text
SenseVoice 识别 -> phrases.json 替换 -> 可选 Qwen 优化 -> 粘贴
```

- Qwen prompt 保持短而保守：只修正语音识别错误、错别字、同音词、标点和断句，不扩写，不解释。
- 文本优化器使用 `local_files_only=True`，运行时不会偷偷下载模型。
- 启动帮助中会显示当前选择的文本优化器。

### 验证

- 确认两个本地 Qwen 目录都有必要文件。
- 确认 Transformers 可以读取 tokenizer/config：
  - `model/千问3-0.6B`
  - `model/千问3-1.7B`
- 已运行 Python 语法检查：

```powershell
python -m py_compile sensevoice_ime.py
```

### 说明

- `model/` 目录继续被 git 忽略，不会上传模型权重。
- Qwen3-1.7B 对中英混合技术口语的修正更稳；Qwen3-0.6B 更快。

## 早期里程碑

### v0.3.3 - 录音音效

- 新增开始/停止录音音效。
- 支持内置蜂鸣、静音或通过 `config.json` 指定自定义 WAV 文件。

### v0.3.2 - 热键拦截与配置加固

- 新增 `suppress=True`，让按键说话热键在焦点应用收到前被消费。
- 加固最短录音、最长录音、剪贴板行为和空格追加等默认配置。

### v0.3.1 - 热键冲突文档

- 记录热键冲突的原因和规避方式。

### v0.3.0 - 按键说话

- 新增按住录音、松开识别并粘贴的流程。
- 将反引号键规范化为 Python `keyboard` 包使用的 `grave`。

### v0.2.x - SenseVoice 流水线

- 使用 FunASR 加载本地 SenseVoiceSmall。
- 新增麦克风录音、临时 WAV、常用词替换和自动粘贴。
- 新增 RMS 静音跳过逻辑。

### v0.1.0 - 独立 MVP

- 创建独立 Python MVP，包含配置、常用词规则、运行脚本和依赖列表。
