# 蓝蓝桌宠（DesktopPetAI）设计文档

## 项目概述

基于 **Python + PySide6 (Qt6)** 开发的 Windows 桌面 AI 悬浮伴侣，常驻桌面，目标形态为"贾维斯式智能管家"。
角色为英雄联盟格温风格的 Q 版少女「蓝蓝」，以透明悬浮窗常驻桌面，支持气泡式对话、文字/语音双模输入、通义千问大模型对话、语音合成播报、系统操作执行（function calling）、日程提醒、主动关怀与长期记忆；同时具备完整的多帧动画互动体验（跳跃 / 压扁回弹 / 抖动 / 跑动 / 摸摸头 / 喂食 / 走路 / 咖啡 / 睡觉 / 随机坐下待机）。

## 角色形象与素材

| 项 | 说明 |
|---|---|
| 角色名 | 蓝蓝 |
| 形象 | 英雄联盟·格温风格 Q 版少女：浅蓝渐变双马尾卷发、黑色大蝴蝶结、蓝绿色颈链、黑色露肩短袖连衣裙、Q 版手办质感 |
| 来源 | 用户提供参考图 + seedream 图生图生成动作帧；绿幕抠图转透明 |
| 动画 | 13 个状态 72 帧透明 PNG（512×512 RGBA）：idle / sit / blink / chat / jump / shake / run-left / run-right / pet-head / feed / walk / coffee / sleep / reminder |
| 交互反馈 | 点击轮流触发跳跃→压扁回弹→左右抖动；拖拽播放跑动动画；随机坐下待机（35% 概率）；互动随机中文气泡 |

## 技术栈

| 组件 | 选型 | 说明 |
|---|---|---|
| GUI | PySide6 (Qt6) | 无边框透明置顶窗口、QMediaPlayer 音频播放、QPropertyAnimation 动画 |
| AI 对话 | 通义千问 (qwen-turbo) | DashScope 兼容 OpenAI 接口，支持 function calling |
| 语音合成 | Qwen-TTS / OpenAI 兼容 TTS | 多引擎可选（设置里切换），播放速率 1.25×，本地文件播放 |
| 语音识别 | Qwen-Audio-ASR | base64 上传 WAV，后台线程识别 |
| 录音 | sounddevice + numpy | 16kHz 单声道 float32 |
| 全局热键 | pynput | 跨平台 GlobalHotKeys |
| 图像处理 | Pillow + numpy | 绿幕抠图、边缘羽化、帧缩放 |
| 系统操作 | pycaw / PyGetWindow / psutil / screen-brightness-control | 音量 / 窗口 / 亮度 / 系统信息 |
| 长期记忆 | SQLite + Qwen text-embedding-v3 | 本地向量检索，numpy 余弦相似度 |
| 打包 | PyInstaller | onedir 模式，直接双击 EXE 运行 |

## 目录结构

```
DesktopPetAI/
├── main.py                     # 程序入口
├── config.py                   # 配置管理（JSON 读写、默认值合并）
├── config.json                 # 用户配置（含 API Key，已 gitignore，不入库）
├── design.md                   # 本文件
├── requirements.txt            # Python 依赖
├── assets/
│   ├── anim/                   # 72 帧动画（13 状态）
│   ├── character.png           # 角色透明主图
│   ├── tray_icon.png           # 托盘图标
│   ├── app.ico                 # 应用多尺寸 ico
│   └── avatar_src.webp         # 原始形象图
├── ui/
│   ├── pet_window.py           # 主悬浮窗（整合所有模块）
│   ├── chat_bubble.py          # 对话气泡（user/ai 双角色、10s 自动淡出）
│   ├── chat_popup.py           # 备用聊天弹窗
│   ├── input_bar.py            # 极简输入条（发送/语音/取消）
│   ├── confirm_bubble.py       # 操作确认气泡（逐次批准）
│   └── settings_dialog.py      # 设置面板（AI/外观/语音/管家/记忆/通用）
├── core/
│   ├── ai_engine.py            # 通义千问引擎 + ChatWorker（工具循环+打字机）
│   ├── tts_engine.py           # Qwen-TTS 合成 + QMediaPlayer 播放（1.25×）
│   ├── asr_engine.py           # Qwen-Audio-ASR 识别 + ASRWorker
│   ├── audio_recorder.py       # sounddevice 录音到 WAV bytes
│   ├── animator.py             # 角色动画状态机（优先级抢占 + 眨眼 + 压扁回弹）
│   ├── hotkey.py               # 全局热键管理
│   ├── reminders.py            # 提醒调度器（持久化 reminders.json）
│   ├── proactive.py            # 主动关怀引擎（空闲/整点/久坐）
│   ├── memory.py               # 长期记忆（SQLite + embedding 向量检索）
│   └── tools/
│       ├── __init__.py         # 导出 SCHEMAS/run/needs_confirm/is_forbidden
│       └── system_tools.py     # 15 个系统操作工具 + 安全策略
├── utils/
│   ├── resource_path.py        # 资源路径解析（兼容 PyInstaller）
│   └── screen.py               # 多屏坐标工具（虚拟桌面/屏幕缩放）
├── aigirl-desktop-pet/         # Electron 素材管线工程（种子工程脚手架 + 素材 QA）
│   ├── app/                    # Electron 应用（素材处理/QA 工具，素材已迁移至 assets/）
│   └── pet-spec.json           # 桌宠规格（状态/互动/素材定义）
├── selftest*.py                # 开发自检脚本
└── 打包产物（不提交）：dist/ build/ .pyi-tmp/ venv/ .pip-cache/
```

## 核心设计决策

### 1. 气泡式对话（非面板）
- 对话全部通过角色头顶的漫画气泡呈现：AI 气泡（白色）+ 用户气泡（蓝色），尾巴指向角色，不遮挡角色。
- 输入为极简悬浮条（一行输入框 + 发送/语音/取消按钮），不显示历史。
- **空闲自动隐藏**：对话结束后 10 秒无操作（点击/拖拽/滚轮/键盘）气泡自动淡出；期间任何操作重置计时。

### 2. 安全策略（双重保障，不可绕过）
- **绝对禁止**：关机 / 重启 / 删除 / 格式化 / 注册表修改等有害操作，代码层直接拦截拒绝。
- **逐次确认**：所有会改动电脑的操作（打开应用/文件、搜索、调音量/亮度、窗口管理、创建文件）每次弹确认气泡，不记忆"总是允许"。
- **System Prompt 强制注入**：安全规则追加到 system_prompt 末尾 + TOOL_USAGE_RULES 强制工具调用。

### 3. Function Calling 工具循环
- ChatWorker（QThread）内循环：非流式请求 → 有 tool_calls 则执行并回填 → 直到模型返回 content → 打字机输出。
- 工具执行结果以 OpenAI 兼容 tool message 回填，模型可多轮使用；单轮最多 6 次工具往返防死循环。
- `temperature=0.3` + `enable_thinking=False` 提升工具调用稳定性。

### 4. 角色动画系统
- Animator（QTimer 60fps）驱动：frameChanged（帧切换）+ offsetChanged（浮动）+ scaleChanged（缩放/压扁回弹）。
- 优先级抢占：reminder(95) > run(90) > chat/pet-head/feed/walk/coffee/sleep(85) > jump(70) > shake(60) > blink(30) > sit(15) > idle(10)。
- 基态语义：IDLE（呼吸浮动）/ TALKING（快速脉动）/ THINKING（左右摇摆）/ LISTENING（放大浮动）；眨眼随机 2.5~5.5s。
- 点击互动轮转：跳跃 → 压扁回弹（320ms 挤压/回弹/稳定）→ 左右抖动。
- **坐姿待机**：空闲 7~13s 随机触发，35% 概率播放 4 帧坐姿动画（9s 后自动起身），其余触发抖动/跳跃并弹气泡。

### 5. 异步线程模型
- ChatWorker：后台对话 + 工具执行 + 打字机；ASRWorker：后台语音识别。
- 确认机制：threading.Event 跨线程阻塞等待 UI 确认；TTS：QMediaPlayer 异步播放。

### 6. 多屏适配
- 以「虚拟桌面」（所有显示器几何并集，含负坐标）为坐标基准，角色可自由拖到副屏。
- 气泡/输入条/确认框按角色所在屏幕 DPI/分辨率自适应缩放（因子限幅 [0.6, 1.6]）。

### 7. 长期记忆
- 本地 SQLite `memory.db` + 通义 `text-embedding-v3` 向量化 + numpy 余弦检索（无重依赖）。
- 对话结束后后台线程用 LLM 自动抽取用户事实；按本轮输入检索 top-k 注入 system prompt。
- embedding/网络失败时优雅降级为"最近记忆"；记忆仅存本地，不入库。

## 版本历史

| 版本 | 日期 | 内容 |
|---|---|---|
| v1.0.0 | 2026-09-17 | 基础桌宠：透明置顶窗口 + 拖拽、气泡对话、通义千问流式对话、TTS 四音色、ASR 语音输入、全局热键、托盘菜单、设置面板、config 持久化 |
| v1.1.0 | 2026-09-17 | 动态形象：AI 抠图透明角色、眨眼帧、Animator 五状态动画、应用图标、启动 bat |
| v1.2.0 | 2026-09-17 | 贾维斯 P1+P2：15 个系统操作工具 + 逐次确认气泡、提醒调度器、主动关怀引擎、Windows 托盘通知、设置新增"管家"页 |
| v1.2.1 | 2026-09-18 | Bug 修复：确认气泡重复弹出、ChatWorker 信号命名、create_file 工具 |
| v1.2.2 | 2026-09-18 | 多屏拖拽修复（虚拟桌面坐标）、10 秒无操作自动淡出气泡 |
| v1.3.0 | 2026-09-18 | 聊天框多屏自适应 + 长期记忆（SQLite + embedding 注入）、设置新增"记忆"页 |
| v1.3.1 | 2026-09-18 | 修复"假装执行"（TOOL_USAGE_RULES 强制工具调用）、TTS 乱码清理 |
| v2.0.0 | 2026-09-18 | PyQt5 → PySide6 (Qt6) 全面迁移；整合 Electron 素材管线 72 帧动画；气泡 10s 无操作自动消失；TTS 1.25× 倍速；新增坐姿待机状态；PyInstaller 打包 EXE 并部署桌面 |
| v2.1.0 | 2026-09-18 | TTS 播放修复（先下载本地再播放，避免流媒体断流/URL 过期导致语音截断）；新增 OpenAI 兼容 TTS 引擎（设置可切换通义/OpenAI 并自由选择音色）；对话 API 地址可配置（支持其他大模型）；AI/用户气泡互不重叠（自动避让上移）；幽灵副屏检测（桌宠不会跑到已拔出的显示器上） |

## 功能清单

- 透明无边框、始终置顶、左键拖拽（带跑动动画）、滚轮缩放（100–360px）
- 点击轮流互动：跳跃 → 压扁回弹 → 左右抖动，随机中文气泡（不遮挡角色）
- 右键菜单：陪我聊聊天 / 语音说话 / 摸摸头 / 喂吃的 / 让她走路 / 请她喝咖啡 / 让她睡觉 / 跟随鼠标 / 调整大小 / 始终置顶 / 设置 / 重置对话 / 隐藏 / 退出程序
- 闲时随机互动：抖动、跳跃、坐下待机（35%）
- AI 对话（通义千问或任意 OpenAI 兼容 API）+ 打字机气泡 + TTS 语音回复（1.25×，通义/OpenAI 多音色）+ ASR 语音输入
- 气泡智能避让：AI 气泡与用户气泡同时显示时自动上移错开，永不重合
- 15 个系统操作工具（开应用/文件、搜索、音量、亮度、窗口管理、系统信息、时间、提醒管理）
- 日程提醒 + 托盘通知 + 主动问候（空闲/整点/久坐）
- 长期记忆（SQLite + 向量检索 + 注入）
- 全局热键：Ctrl+Shift+Space 聊天 / Ctrl+Shift+V 语音
- 多屏适配、DPI 自适应、10s 无操作气泡自动隐藏

## 依赖清单

```
PySide6>=6.6
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
pyinstaller>=6.0   # 打包时
```

可选（仅形象制作时）：rembg, onnxruntime

## 运行方式

```bash
cd E:\DesktopPetAI
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python main.py
```

首次运行在设置中填写通义千问 API Key（config.json 本地保存，不入库）。

## 打包与分发

```bash
set TMP=E:\DesktopPetAI\.pyi-tmp
set TEMP=E:\DesktopPetAI\.pyi-tmp
venv\Scripts\pyinstaller --noconfirm --clean --onedir --windowed --name "蓝蓝桌宠" ^
  --icon assets\app.ico --add-data "assets;assets" ^
  --collect-all pycaw --collect-submodules comtypes ^
  --collect-all screen_brightness_control main.py
```

- 产物：`dist\蓝蓝桌宠\蓝蓝桌宠.exe`（需保留整个目录，`_internal` 不可删除）
- 部署：复制整个目录到桌面即可直接双击运行；首次启动自动在 EXE 同目录生成 config.json

## 路线图

- P4: 唤醒词免按键（本地 KWS + VAD）
- P5: 流式连续对话 + 语音打断
- P6: 屏幕视觉理解（qwen-vl 读屏）
- P7: 情绪-动画联动 + 天气/资讯工具
- P8: 安全加固、开机自启、单文件安装包

## 参考项目

- https://github.com/jiang-0827/AI-girl （桌面 AI 伴侣示例 / 仓库基线）
