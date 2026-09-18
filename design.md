# 桌面 AI 悬浮伴侣 (DesktopPetAI) - 设计文档

## 项目概述

基于 Python + PyQt5 开发的桌面 AI 悬浮伴侣应用，目标形态为"贾维斯式智能管家"。角色以透明悬浮窗常驻桌面，支持气泡式对话、文字/语音双模输入、通义千问大模型对话、语音合成播报、系统操作执行（function calling）、定时提醒与主动关怀。

## 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| GUI | PyQt5 | 无边框透明置顶窗口、QMediaPlayer 音频播放 |
| AI 对话 | 通义千问 (qwen-turbo/plus/max) | DashScope 兼容 OpenAI 接口，支持 function calling |
| 语音合成 | qwen-tts | Cherry/Serena/Ethan/Chelsie 四音色 |
| 语音识别 | qwen-audio-asr | base64 上传 WAV，后台线程识别 |
| 录音 | sounddevice + numpy | 16kHz 单声道 float32 |
| 全局热键 | pynput | 跨平台 GlobalHotKeys |
| 图像处理 | Pillow + rembg | 抠图透明化、眨眼帧生成 |
| 系统操作 | pycaw/pygetwindow/psutil/screen-brightness-control | 音量/窗口/亮度/系统信息 |
| 配置 | JSON 文件 | 持久化用户设置 + 提醒 |

## 项目结构

```
DesktopPetAI/
├── main.py                     # 程序入口（高分屏适配、首次引导）
├── config.py                   # 配置管理（JSON 读写、默认值合并）
├── requirements.txt            # Python 依赖
├── design.md                   # 本文件
├── assets/
│   ├── character.png           # 角色透明主图（rembg 抠图）
│   ├── character_blink.png     # 眨眼帧（程序生成）
│   ├── tray_icon.png           # 托盘图标（头像缩略）
│   ├── app.ico                 # 应用多尺寸 ico
│   └── avatar_src.webp         # 原始形象图（供重生成用）
├── ui/
│   ├── pet_window.py           # 主悬浮窗（整合所有模块）
│   ├── chat_bubble.py          # 对话气泡（user/ai 双角色、漫画式）
│   ├── input_bar.py            # 极简输入条（发送/语音/取消）
│   ├── confirm_bubble.py       # 操作确认气泡（逐次批准）
│   └── settings_dialog.py      # 设置面板（AI/外观/语音/管家/通用）
├── core/
│   ├── ai_engine.py            # 通义千问引擎 + ChatWorker（工具循环+打字机）
│   ├── tts_engine.py           # Qwen-TTS 合成 + QMediaPlayer 播放
│   ├── asr_engine.py           # Qwen-Audio-ASR 识别 + ASRWorker
│   ├── audio_recorder.py       # sounddevice 录音到 WAV bytes
│   ├── animator.py             # 角色动画（呼吸/说话/思考/聆听/眨眼）
│   ├── hotkey.py               # 全局热键管理
│   ├── reminders.py            # 提醒调度器（持久化 reminders.json）
│   ├── proactive.py            # 主动关怀引擎（空闲/整点/久坐）
│   └── tools/
│       ├── __init__.py          # 导出 SCHEMAS/run/needs_confirm/is_forbidden/describe
│       └── system_tools.py      # 15 个系统操作工具 + 安全策略
├── utils/
│   └── resource_path.py        # 资源路径解析（兼容 PyInstaller）
├── generate_assets.py          # 占位图生成脚本
├── process_avatar.py           # 形象抠图脚本（rembg）
├── make_animation.py           # 眨眼帧+图标生成脚本
├── make_bat.py                 # 启动 bat 生成脚本
└── download_model.py           # rembg u2net 模型镜像下载
```

## 核心设计决策

### 1. 气泡式对话（非面板）
- 去掉传统聊天面板，对话全部通过角色头顶的漫画气泡呈现。
- 双气泡：用户气泡（蓝色，左上）+ AI 气泡（白色，右上），尾巴指向角色。
- 输入为极简悬浮条（一行输入框 + 发送/语音/取消按钮），不显示历史。

### 2. 安全策略（双重保障，不可绕过）
- **绝对禁止**：关机/重启/删除/格式化/注册表修改等有害操作，代码层直接拦截拒绝。
- **逐次确认**：所有会改动电脑的操作（打开应用/文件、搜索、调音量/亮度、窗口管理、创建文件）每次弹窗向用户确认，不记忆"总是允许"。
- **System Prompt 强制注入**：安全规则追加到 system_prompt 末尾，无论用户如何配置都生效。

### 3. Function Calling 工具循环
- ChatWorker（QThread）内循环：非流式请求 → 若有 tool_calls 执行并回填 → 直到模型返回 content → 打字机流式输出。
- 工具执行结果以 OpenAI 兼容 tool message 格式回填，模型可多轮使用。
- 单轮最多 MAX_TOOL_STEPS=6 次工具往返，防无限循环。

### 4. 角色动画系统
- Animator（QTimer 30fps）驱动：offsetChanged（浮动）+ scaleChanged（缩放）+ blinkChanged（眨眼帧切换）。
- 五状态：IDLE（呼吸浮动）/ TALKING（快速脉动）/ THINKING（左右摇摆）/ LISTENING（放大+浮动）/ 眨眼（随机 2.5~5.5s 间隔）。
- 眨眼用两张透明 PNG 实时切换（避免 GIF 白边问题）。

### 5. 异步线程模型
- ChatWorker: 后台对话 + 工具执行 + 打字机
- ASRWorker: 后台语音识别
- 确认机制: threading.Event 跨线程阻塞等待 UI 确认
- TTS: QMediaPlayer 异步播放，信号通知状态

## 版本历史

### v1.0.0 - 基础桌宠 (2026-09-17)
- PyQt5 无边框透明置顶窗口 + 拖拽
- 气泡式对话（user/ai 双 ChatBubble）
- InputBar 极简输入条（文字 + 取消）
- 通义千问 qwen-turbo 流式对话
- Qwen-TTS 语音播报（4 音色）
- Qwen-Audio-ASR 语音输入（热键 Ctrl+Shift+V）
- 全局热键（pynput）
- 系统托盘 + 右键菜单
- 设置面板（AI/外观/语音/通用）
- config.json 持久化
- 首次运行引导

### v1.1.0 - 动态形象 (2026-09-17)
- rembg AI 抠图生成透明角色图
- 眨眼帧程序生成（皮肤采样+睫毛线）
- Animator 五状态动画（呼吸/说话/思考/聆听/眨眼）
- 应用图标（tray_icon.png + app.ico）
- 启动 bat 脚本

### v1.2.0 - 贾维斯 P1+P2 (2026-09-17)
- Function calling 工具循环（ChatWorker 重构）
- 15 个系统操作工具（open_app/open_file/create_file/search_file/set_volume/get_volume/set_brightness/list_windows/focus_window/close_window/system_status/get_datetime/create_reminder/list_reminders/cancel_reminder）
- 安全策略：禁止有害操作 + 逐次确认气泡
- 提醒调度器（ReminderScheduler + reminders.json 持久化）
- 主动关怀引擎（空闲问候/整点报时/久坐提醒）
- Windows 托盘通知
- 设置面板新增"管家"标签页

### v1.2.1 - Bug 修复 (2026-09-18)
- 修复确认气泡只能弹一次的 bug（QThread.finished 信号覆盖 + 复用顶层窗口）
- 重命名 ChatWorker.finished → replyFinished（避免覆盖 QThread 内置信号）
- 确认气泡每次新建实例（避免 Qt.Tool 窗口 hide 后 show 不可靠）
- worker 完成后清理引用（self.worker = None）
- ConfirmBubble.ask() 增加 activateWindow + raise_ 确保前台显示
- 新增 create_file 工具（支持创建记事本文件）

## 依赖清单

```
PyQt5>=5.15
requests>=2.28
pynput>=1.7
Pillow>=9.0
sounddevice>=0.4
numpy>=1.24
psutil>=5.9
pycaw>=20240101
comtypes>=1.2
screen-brightness-control>=0.20
PyGetWindow>=0.0.9
```

可选（仅形象制作时需要）：rembg, onnxruntime

## 运行方式

```bash
cd E:\DesktopPetAI
python main.py
# 或双击 启动桌宠.bat
```

## 后续路线图

- P3: 长期记忆（SQLite + 向量检索 + embedding 注入）
- P4: 唤醒词免按键（本地 KWS + VAD）
- P5: 流式连续对话 + 语音打断
- P6: 屏幕视觉理解（qwen-vl 读屏）
- P7: 情绪-动画联动 + 天气/资讯工具
- P8: 打包独立 exe + 开机自启注册表

## 参考项目

- https://github.com/jiang-0827/AI-girl （桌面 AI 伴侣示例）
