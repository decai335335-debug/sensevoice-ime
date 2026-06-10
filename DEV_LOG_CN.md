# SenseVoice IME MVP 开发日志

## 1. 项目起源

最初的需求是把本地已下载的 SenseVoiceSmall 模型变成一个实用的语音输入法。用户本地已有模型：

```text
model/SenseVoiceSmall
```

与其立即修改庞大的 OpenWhispr Electron 应用，不如先做一个最小可用版本（MVP），验证完整的本地闭环：

1. 采集麦克风音频。
2. 运行本地 SenseVoiceSmall 推理。
3. 应用常用词替换。
4. 将识别到的文字粘贴到当前输入框。
5. 用键盘快捷键控制整个流程。

这个 MVP 最初在 OpenWhispr 仓库的 `sensevoice_ime_mvp/` 目录下创建，随后被提取为独立文件夹，并附带了一份本地模型副本。

## 2. 迭代时间线

### v0.1.0 - 独立 MVP 脚手架

创建了独立文件夹，包含：

- `sensevoice_ime.py`
- `config.json`
- `phrases.json`
- `requirements.txt`
- `run.bat`
- `test_model.bat`

决策：先把 MVP 做成 Python 旁路程序，因为将 SenseVoice 集成到完整的 Electron 应用需要改动主进程、渲染层状态、模型管理和打包流程，范围太大。

### v0.2.0 - 本地 SenseVoice 流水线

验证 FunASR 可以加载本地模型：

```python
AutoModel(model="model/SenseVoiceSmall", trust_remote_code=False)
```

对自带的 `example/zh.mp3` 测试成功输出：

```text
??????9???????
```

新增功能：

- 固定时长测试命令
- 模型测试命令
- 麦克风设备列表
- 常用词替换 JSON
- 自动剪贴板粘贴

### v0.2.1 - 静音守卫

1 秒的安静录音产生了误识别（`Yeah.`）。添加了 RMS 音量测量和 `min_rms` 阈值，低于阈值的录音在推理/粘贴前会被跳过。

默认值：

```json
"min_rms": 0.003
```

### v0.3.0 - 按键说话热键

用户希望用 Ctrl+反引号作为按住录音的快捷键：

- 按下并按住：开始录音。
- 松开：停止录音。
- 随后进行转写和粘贴。

最初实现使用了 `keyboard.add_hotkey(... trigger_on_release=True)`，但组合键的松开行为不太可靠。实现改为更低层级的监听器：

- 监听 `grave` 键按下
- 确认 `ctrl` 当前被按住
- 开始录音
- 当 `grave` 或 `ctrl` 任一松开时停止

面向用户的配置保持：

```json
"push_to_talk_hotkey": "ctrl+`"
```

内部将反引号统一映射为 `grave`，以适配 Python `keyboard` 包。

### v0.3.1 - 热键冲突文档

观察到 Codex 可能会把 Ctrl+反引号占为自己的终端行为。新增 FAQ 说明：应用级快捷键可能阻止全局监听器收到事件，用户可以在 `config.json` 中修改 `push_to_talk_hotkey`。

### v0.3.2 - 热键拦截与配置加固

即使做了按键说话，VS Code / Codex 等应用仍会拦截 Ctrl+反引号，因为全局热键监听器默认不会阻止事件继续传到焦点应用。为 `keyboard.add_hotkey` 增加了 `suppress=True`，让组合键在到达活动应用之前就被消费掉。

同时加固了 `config.json` 默认值：

- `min_record_seconds`: 0.3（避免快速点击误触发）
- `max_record_seconds`: 60（安全上限，防止录音失控）
- `restore_clipboard`: false（默认不恢复，避免意外丢失剪贴板内容）
- `append_space`: false（默认不追加空格）

修复了 `config.json` 中默认 `push_to_talk_hotkey` 被误改为仅反引号的问题，恢复为 `ctrl+\``。

## 3. 踩坑记录

| 问题 | 根因 | 解决方案 | 版本 |
| --- | --- | --- | --- |
| 直接集成到 OpenWhispr 对 MVP 来说太大 | Electron 应用已有大量模型、录音和 UI 路径 | 先构建独立的 Python 旁路程序 | v0.1.0 |
| 本地模型可能需要远程代码 | SenseVoice 示例常使用 `trust_remote_code=True` | 验证本地 FunASR 集成路径可以用 `trust_remote_code=False` | v0.2.0 |
| 安静录音产生虚假文字 | ASR 可能对短噪音或静音产生幻觉 | 添加 RMS 阈值和跳过逻辑 | v0.2.1 |
| ctrl+反引号无法直接解析 | Python `keyboard` 包在热键字符串中对反引号有特殊处理 | 将反引号规范化为 `grave` | v0.3.0 |
| 松开事件不够可靠 | 组合键松开处理可能不一致 | 对触发键和修饰键分别使用 `on_press_key` 和 `on_release_key` | v0.3.0 |
| Codex 等应用占用 Ctrl+反引号 | 应用级快捷键可能在全局监听器之前执行 | 记录冲突并支持修改 `push_to_talk_hotkey` | v0.3.1 |
| 某些应用不接受模拟粘贴 | 应用安全策略或焦点状态阻止了 `Ctrl+V` | 保留识别结果在剪贴板，并文档化管理员权限/焦点 workaround | v0.3.1 |
| 热键仍会传到焦点应用 | `keyboard` 默认会把组合键转发给活动窗口 | 添加 `suppress=True` 拦截事件 | v0.3.2 |
| 默认热键被误改成仅反引号 | 本地测试时改了 `config.json` 但未同步文档 | 恢复默认值为 `ctrl+\`` 并在文档中明确说明 | v0.3.2 |

## 4. 设计决策

### 为什么用 Python 旁路程序，而不是直接改 OpenWhispr？

| 选项 | 优点 | 缺点 | 决策 |
| --- | --- | --- | --- |
| 修改完整的 OpenWhispr Electron 应用 | 原生产品集成 | 影响面大，构建/打包工作更多 | MVP 阶段不做 |
| Python 旁路程序 | 构建快，可直接使用 FunASR，易于测试 | 基于控制台，不够精致 | **选定** |
| 完整 Windows IME 驱动 | 最好的原生输入体验 | 复杂度极高 | 仅未来考虑 |

### 为什么用剪贴板粘贴？

真正的输入法需要操作系统级集成。对于 MVP 来说，剪贴板粘贴能在大多数文本框里工作，并避免了 Windows IME 驱动的复杂性。即使粘贴失败，识别结果也仍然保留在剪贴板中。

### 为什么用按键说话（Push-To-Talk）？

按键说话避免了全天候监听，让用户拥有直接控制权。它也减少了意外录音，并且在第一版中比自动 VAD 更容易理解和调试。

### 为什么用 JSON 做常用词替换？

一个简单的 JSON 列表就足以修正常见误识别，无需构建设置界面。它透明、可编辑，并且支持运行时热重载。

### 为什么要拦截热键？

如果不拦截，已经绑定了相同快捷键的焦点应用（例如 VS Code 用 `Ctrl+\`` 打开集成终端）会在我们的全局监听器之前或同时响应。这会导致用户只想听写时终端却被打开。`keyboard` 包的 `suppress=True` 可以消费掉该事件，阻止其继续传递。

## 5. 实际测试数据

| 测试项 | 结果 |
| --- | --- |
| FunASR 依赖安装 | 成功 |
| 本地 SenseVoiceSmall 模型路径存在 | 成功 |
| 模型在 `cuda:0` 上加载 | 成功 |
| `--test-model` 测试 `example/zh.mp3` | 成功，识别出中文句子 |
| `--list-devices` | 成功，检测到默认输入设备 |
| `--once 1 --no-paste` 安静录音 | 添加 RMS 阈值后被跳过 |
| ctrl+反引号解析 | 直接在 `keyboard` 中失败，规范化为 `ctrl+grave` 后成功 |
| 按键说话解析器 | ctrl+反引号映射为修饰键 `['ctrl']` 和触发键 `grave` |
| VS Code 中热键拦截 | 成功；按住 `Ctrl+\`` 听写时不再弹出终端 |
| `min_record_seconds` 守卫 | 快速轻触被丢弃，不会触发误识别 |

## 6. 文件位置

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

## 当前已知限制

- 它不是原生 Windows IME 驱动。
- 使用剪贴板粘贴，某些应用可能会阻止或重定向粘贴操作。
- 热键仍可能与在更低层面占用 Ctrl+反引号的应用（如 Codex）冲突。
- 控制台窗口必须保持打开状态。
- 目前只能选择系统默认麦克风。
