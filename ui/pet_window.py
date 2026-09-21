"""主悬浮窗 - 无边框、透明、置顶桌宠

整合能力：
- 多帧动画（13 状态 68 帧）：idle/blink/chat/jump/shake/run/pet-head/feed/walk/coffee/sleep/reminder
- 左键点击轮流互动：跳跃 → 压扁回弹 → 左右抖动；互动随机中文气泡
- 拖拽移动：播放跑动动画；滚轮调整大小；右键互动菜单；跟随鼠标
- AI 能力：气泡对话（打字机+工具循环）、TTS、ASR、热键、提醒、主动关怀、长期记忆
"""
import os
import math
import random
from PySide6.QtCore import Qt, QPoint, QRect, QTimer, QEvent
from PySide6.QtGui import QPixmap, QIcon, QCursor
from PySide6.QtWidgets import (
    QWidget, QLabel, QMenu, QApplication, QSystemTrayIcon
)

from config import load_config, save_config
from utils.screen import clamp_to_virtual, clamp_to_screen, screen_scale
from core.animator import Animator
from core.ai_engine import AIEngine, ChatWorker
from core.hotkey import HotkeyManager
from core.tts_engine import TTSEngine
from core.asr_engine import ASREngine, ASRWorker
from core.audio_recorder import AudioRecorder, MAX_SECONDS
from core.reminders import ReminderScheduler
from core.proactive import ProactiveEngine
from core.memory import MemoryStore
from ui.chat_bubble import ChatBubble
from ui.input_bar import InputBar
from ui.confirm_bubble import ConfirmBubble
from ui.settings_dialog import SettingsDialog
from utils.resource_path import resource_path

# 本轮对话结束后，无操作多久自动淡出气泡（毫秒）
IDLE_HIDE_MS = 10000

# 互动气泡文案（简短、有趣、中文）
TAP_TEXT = {
    'jump': ["嘿！跳起来啦！", "陪你玩一下~", "嘿嘿，看我跳得多高！", "活动一下筋骨！"],
    'shake': ["咦？摇摇晃晃~", "别晃啦，晕乎乎的~", "左右摇摆，真开心！", "抖一抖，精神好！"],
    'squash': ["哎呀！被压扁啦！", "呼~弹回来了！", "嘿嘿，再来一次！", "软软的，很好捏！"],
}
IDLE_TEXTS = [
    "今天过得怎么样呀？", "我好无聊哦~", "要不要摸摸我的头？",
    "想听我讲个小秘密吗？", "你敲键盘的声音好好听~", "陪我玩一下嘛！",
    "在忙什么呀？", "嘿嘿，我一直在看着你哦~",
]
PET_HEAD_TEXTS = ["呜…好舒服~", "再摸摸嘛", "被你摸头最幸福啦", "头发都摸乱啦！"]
FEED_TEXTS = ["好好吃！谢谢~", "甜点最棒啦！", "再来一块嘛~", "呜…太好了"]
WALK_TEXTS = ["走一走真开心！", "我们去散步吧~", "活动一下身体~", "跟着我走起来！"]
COFFEE_TEXTS = ["咖啡好香呀~", "暖暖的，好幸福", "谢谢你的咖啡！", "再来一杯嘛~"]
SLEEP_TEXTS = ["晚安啦…", "好困呀，呼~", "做个好梦…", "嘘…睡着了"]

# 右键"调整大小"档位
SIZE_LEVELS = [(120, "小"), (176, "中"), (220, "大"), (300, "超大")]


class PetWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.cfg = load_config()
        self._drag_pos = None
        self._base_pos = QPoint(100, 100)
        self._anim_offset = QPoint(0, 0)
        self._scale = 1.0
        self._frame = None
        self._reply_buf = ""
        self._recording = False
        self._click_seq = 0          # 点击互动轮转序号
        self._dragging = False
        self._last_drag_x = 0

        # 角色标签（多帧动画显示）
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)

        # 动画状态机
        self.animator = Animator(self)
        self.animator.frameChanged.connect(self._on_frame)
        self.animator.offsetChanged.connect(self._on_offset)
        self.animator.scaleChanged.connect(self._on_scale)

        # 两个气泡：AI（右上）+ 用户（左上）
        self.ai_bubble = ChatBubble(role="ai", align="left")
        self.user_bubble = ChatBubble(role="user", align="right")

        # 输入条
        self.input_bar = InputBar()
        self.input_bar.sendRequested.connect(self._on_send)
        self.input_bar.voiceToggled.connect(self._toggle_voice_input)

        # AI 引擎
        self.engine = AIEngine(
            self.cfg.get("api_key", ""),
            self.cfg.get("model", "qwen-turbo"),
            self.cfg.get("system_prompt", ""),
            self.cfg.get("llm_base_url", ""),
        )
        self.worker = None

        # 长期记忆
        self.memory = MemoryStore(
            api_key=self.cfg.get("api_key", ""),
            chat_model=self.cfg.get("model", "qwen-turbo"),
            topk=int(self.cfg.get("memory_topk", 4)),
            enabled=bool(self.cfg.get("enable_memory", True)),
        )
        self.engine.memory = self.memory

        # 语音引擎
        self.tts = TTSEngine(
            self.cfg.get("api_key", ""),
            self.cfg.get("tts_voice", "Cherry"),
            self,
            provider=self.cfg.get("tts_provider", "qwen"),
            base_url=self.cfg.get("tts_base_url", ""),
            model=self.cfg.get("tts_model", ""),
        )
        self.tts.speakStarted.connect(lambda: self.animator.set_state(Animator.TALKING))
        self.tts.speakFinished.connect(self._on_speak_finished)
        self.tts.error.connect(lambda m: self._show_ai_bubble("语音播报失败啦"))
        self.asr = ASREngine(self.cfg.get("api_key", ""))
        self.recorder = AudioRecorder()
        self.asr_worker = None
        self._rec_timer = QTimer(self)
        self._rec_timer.setSingleShot(True)
        self._rec_timer.timeout.connect(self._stop_recording)

        # 确认气泡（逐次批准）
        self.confirm_bubble = ConfirmBubble()
        self.confirm_bubble.confirmed.connect(self._on_confirm_resolved)
        self._pending_confirm_worker = None

        # 提醒调度器
        self.reminders = ReminderScheduler(self._on_reminder_fire, self)

        # 主动关怀
        self.proactive = ProactiveEngine(self.cfg, self)
        self.proactive.speakRequested.connect(self._on_proactive_speak)

        # 工具上下文（供 function calling 使用）
        self.ctx = {
            "add_reminder": self.reminders.add,
            "list_reminders": self.reminders.list_readable,
            "cancel_reminder": self.reminders.cancel,
            "enable_tools": self.cfg.get("enable_tools", True),
        }

        # 空闲自动隐藏气泡：本轮对话结束后 10 秒无操作则淡出
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)

        # 监听全局（本应用内）用户活动，用于重置空闲计时
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        # 闲时随机互动
        self._idle_anim_timer = QTimer(self)
        self._idle_anim_timer.setSingleShot(True)
        self._idle_anim_timer.timeout.connect(self._on_idle_anim)

        # 跟随鼠标
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(33)
        self._follow_timer.timeout.connect(self._follow_tick)

        # 托盘
        self.tray = None
        self._build_tray()

        self._restore_position()
        self._apply_topmost_flag()
        self.setWindowOpacity(max(0.4, self.cfg.get("opacity", 255) / 255.0))
        self._update_display()
        self._sync_screen_scale()  # 启动时按所在屏适配大小

        # 热键
        self.hotkey = None
        self.voice_hotkey = None
        self._start_hotkeys()

        # 启动闲时随机互动
        self._schedule_idle_anim()
        # 启动跟随鼠标（若配置开启）
        if self.cfg.get("follow_mouse", False):
            self._follow_timer.start()

    # ---------- 渲染 ----------
    def _on_frame(self, pm):
        self._frame = pm
        self._update_display()

    def _on_scale(self, s):
        self._scale = s
        self._update_display()

    def _update_display(self):
        size = int(self.cfg.get("pet_size", 176))
        w = max(8, int(size * self._scale))
        h = max(8, int(size * self._scale))
        if self._frame is not None and not self._frame.isNull():
            scaled = self._frame.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.label.setPixmap(scaled)
        self.resize(size + 20, size + 20)
        self.label.move(10, 10)
        self.label.resize(size, size)

    def _on_offset(self, dx, dy):
        self._anim_offset = QPoint(dx, dy)
        self.move(self._base_pos + self._anim_offset)
        self._reposition_bubbles()

    def _reposition_bubbles(self):
        self._sync_bubble_avoid()
        if self.ai_bubble.isVisible():
            x, y = self._ai_tail()
            self.ai_bubble.update_text(self.ai_bubble._text, x, y)
        if self.user_bubble.isVisible():
            x, y = self._user_tail()
            self.user_bubble.update_text(self.user_bubble._text, x, y)

    def _sync_bubble_avoid(self):
        """两个气泡同时显示时互相避让（重叠则上移），避免重合冲突"""
        if self.user_bubble.isVisible():
            self.ai_bubble.set_avoid(self.user_bubble.geometry())
        else:
            self.ai_bubble.set_avoid(None)
        if self.ai_bubble.isVisible():
            self.user_bubble.set_avoid(self.ai_bubble.geometry())
        else:
            self.user_bubble.set_avoid(None)

    def _pet_center(self):
        size = int(self.cfg.get("pet_size", 176))
        return self._base_pos.x() + size // 2, self._base_pos.y() + size // 2

    def _sync_screen_scale(self):
        """根据角色当前所在屏幕，让输入条/气泡/确认框大小自适应主副屏。"""
        cx, cy = self._pet_center()
        f = screen_scale(cx, cy)
        self.input_bar.apply_scale(f)
        self.ai_bubble.apply_scale(f)
        self.user_bubble.apply_scale(f)
        if self.confirm_bubble is not None:
            self.confirm_bubble.apply_scale(f)
        self._reposition_bubbles()
        if self.input_bar.isVisible():
            self._open_input()

    # ---------- 点击互动 / 拖拽 ----------
    def mousePressEvent(self, ev):
        self.note_user_activity()
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPos() - self._base_pos
            self._dragging = False
            self._last_drag_x = ev.globalPos().x()
        elif ev.button() == Qt.RightButton:
            self._show_menu(ev.globalPos())

    def mouseMoveEvent(self, ev):
        if self._drag_pos is not None:
            self._base_pos = ev.globalPos() - self._drag_pos
            dx = ev.globalPos().x() - self._last_drag_x
            self._last_drag_x = ev.globalPos().x()
            self.move(self._base_pos + self._anim_offset)
            if abs(dx) > 2:
                self._dragging = True
                # 拖拽跑动动画：根据水平移动方向
                if dx > 0:
                    self.animator.play('run-right')
                else:
                    self.animator.play('run-left')

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._drag_pos is not None:
            moved = (ev.globalPos() - self._drag_pos) - self._base_pos
            is_click = (not self._dragging) and abs(moved.x()) < 3 and abs(moved.y()) < 3
            self._drag_pos = None
            self._dragging = False
            if is_click and self.cfg.get("interactive", True):
                self._cycle_click_interaction()
            else:
                self.animator.stop_active()
                self._save_position()
                self._sync_screen_scale()  # 可能换到了另一块屏，重算大小

    def wheelEvent(self, ev):
        self.note_user_activity()
        delta = ev.angleDelta().y()
        if delta == 0:
            return
        step = 16 if delta > 0 else -16
        size = int(self.cfg.get("pet_size", 176))
        new_size = max(int(self.cfg.get("pet_size_min", 100)),
                       min(int(self.cfg.get("pet_size_max", 360)), size + step))
        if new_size != size:
            self.cfg["pet_size"] = new_size
            save_config(self.cfg)
            self._update_display()
            self._reposition_bubbles()

    # ---------- 点击互动轮转：跳跃 → 压扁回弹 → 左右抖动 ----------
    def _cycle_click_interaction(self):
        acts = ['jump', 'squash', 'shake']
        act = acts[self._click_seq % len(acts)]
        self._click_seq += 1
        if act == 'squash':
            self.animator.play_squash()
            self._show_anim_bubble(random.choice(TAP_TEXT['squash']))
        else:
            self.animator.play(act)
            self._show_anim_bubble(random.choice(TAP_TEXT[act]))

    # ---------- 闲时随机互动 ----------
    def _schedule_idle_anim(self):
        self._idle_anim_timer.start(random.randint(7000, 13000))

    def _on_idle_anim(self):
        try:
            if not self.cfg.get("random_chatter", True):
                return
            # 对话/录音/输入中不打扰；长互动动画中也不打扰
            if self.worker is not None and self.worker.isRunning():
                return
            if self._recording or self.input_bar.isVisible():
                return
            if self.animator.current_state() in ('walk', 'sleep', 'feed', 'coffee', 'pet-head', 'chat'):
                return
            if self.animator.is_active():
                return
            # 随机：动作 + 气泡
            self.animator.play(random.choice(['shake', 'shake', 'jump']))
            self._show_anim_bubble(random.choice(IDLE_TEXTS))
        finally:
            self._schedule_idle_anim()

    # ---------- 互动气泡（不遮挡角色：位于头顶上方） ----------
    def _show_anim_bubble(self, text: str):
        self._sync_bubble_avoid()
        x, y = self._ai_tail()
        self.ai_bubble.show_text(text, x, y)
        self.ai_bubble.keep_alive(4500)

    # ---------- 菜单 ----------
    def _show_menu(self, global_pos):
        menu = QMenu()
        act_chat = menu.addAction("💬 陪我聊聊天")
        act_voice = None
        if self.cfg.get("enable_asr", True):
            act_voice = menu.addAction("🎤 语音说话")
        menu.addSeparator()
        act_pet = menu.addAction("💗 摸摸头")
        act_feed = menu.addAction("🍰 喂吃的")
        act_walk = menu.addAction("🚶 让她走路")
        act_coffee = menu.addAction("☕ 请她喝咖啡")
        act_sleep = menu.addAction("😴 让她睡觉")
        menu.addSeparator()
        act_follow = menu.addAction("🖱 跟随鼠标")
        act_follow.setCheckable(True)
        act_follow.setChecked(bool(self.cfg.get("follow_mouse", False)))
        # 调整大小子菜单
        size_menu = menu.addMenu("🔍 调整大小")
        cur = int(self.cfg.get("pet_size", 176))
        for px, name in SIZE_LEVELS:
            a = size_menu.addAction(f"{name}（{px}px）")
            a.setCheckable(True)
            a.setChecked(abs(cur - px) <= 8)
            a.triggered.connect(lambda checked, p=px: self._set_pet_size(p))
        act_top = menu.addAction("📌 始终置顶")
        act_top.setCheckable(True)
        act_top.setChecked(bool(self.cfg.get("always_on_top", True)))
        menu.addSeparator()
        act_settings = menu.addAction("⚙ 设置")
        act_reset = menu.addAction("🔄 重置对话")
        act_hide = menu.addAction("👻 隐藏")
        act_quit = menu.addAction("❌ 退出程序")
        chosen = menu.exec(global_pos)
        if chosen == act_chat:
            self._open_input()
        elif chosen == act_voice:
            self._toggle_voice_input()
        elif chosen == act_pet:
            self.animator.play('pet-head')
            self._show_anim_bubble(random.choice(PET_HEAD_TEXTS))
        elif chosen == act_feed:
            self.animator.play('feed')
            self._show_anim_bubble(random.choice(FEED_TEXTS))
        elif chosen == act_walk:
            self.animator.play('walk')
            self._show_anim_bubble(random.choice(WALK_TEXTS))
        elif chosen == act_coffee:
            self.animator.play('coffee')
            self._show_anim_bubble(random.choice(COFFEE_TEXTS))
        elif chosen == act_sleep:
            self.animator.play('sleep')
            self._show_anim_bubble(random.choice(SLEEP_TEXTS))
        elif chosen == act_follow:
            self._toggle_follow(bool(act_follow.isChecked()))
        elif chosen == act_top:
            self._toggle_topmost(bool(act_top.isChecked()))
        elif chosen == act_settings:
            self.open_settings()
        elif chosen == act_reset:
            self.engine.reset()
            self._show_ai_bubble("对话已重置～")
        elif chosen == act_hide:
            self.hide()
        elif chosen == act_quit:
            self._quit()

    def _set_pet_size(self, px: int):
        self.cfg["pet_size"] = px
        save_config(self.cfg)
        self._update_display()
        self._reposition_bubbles()
        self._sync_screen_scale()

    def _toggle_follow(self, on: bool):
        self.cfg["follow_mouse"] = bool(on)
        save_config(self.cfg)
        if on:
            self._follow_timer.start()
            self._show_anim_bubble("好呀，我跟着你走~")
        else:
            self._follow_timer.stop()
            self.animator.stop_active()
            self._save_position()
            self._show_anim_bubble("好啦，我停在这里~")

    def _toggle_topmost(self, on: bool):
        self.cfg["always_on_top"] = bool(on)
        save_config(self.cfg)
        self._apply_topmost_flag()

    def _apply_topmost_flag(self):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(self.cfg.get("always_on_top", True)))
        self.show()

    # ---------- 跟随鼠标 ----------
    def _follow_tick(self):
        if not self.cfg.get("follow_mouse", False):
            return
        try:
            cur = QCursor.pos()
        except Exception:
            return
        size = int(self.cfg.get("pet_size", 176))
        cx = self._base_pos.x() + size // 2
        cy = self._base_pos.y() + size // 2
        dx = cur.x() - cx
        dy = cur.y() - cy
        dist = math.hypot(dx, dy)
        if dist < 26:
            if self.animator.is_active():
                self.animator.stop_active()
            return
        speed = min(max(dist * 0.18, 4), 28)
        nx = self._base_pos.x() + (dx / dist) * speed
        ny = self._base_pos.y() + (dy / dist) * speed
        self._base_pos = QPoint(int(round(nx)), int(round(ny)))
        self.move(self._base_pos + self._anim_offset)
        if abs(dx) > 6:
            self.animator.play('run-right' if dx > 0 else 'run-left')
        elif self.animator.is_active():
            self.animator.stop_active()

    # ---------- 托盘 ----------
    def _build_tray(self):
        icon_path = resource_path("assets/tray_icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.setWindowIcon(icon)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon, self)
            menu = QMenu()
            menu.addAction("💬 聊天", self._open_input)
            if self.cfg.get("enable_asr", True):
                menu.addAction("🎤 语音说话", self._toggle_voice_input)
            menu.addSeparator()
            menu.addAction("⚙ 设置", self.open_settings)
            menu.addAction("显示/隐藏", self._toggle_visible)
            menu.addSeparator()
            menu.addAction("❌ 退出", self._quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._tray_activated)
            self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_visible()

    def _toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self._restore_position()

    # ---------- 输入条 ----------
    def _open_input(self):
        self.input_bar.adjustSize()
        self.note_user_activity()
        size = int(self.cfg.get("pet_size", 176))
        x = self._base_pos.x() + size // 2 - self.input_bar.width() // 2
        y = self._base_pos.y() + size + 16
        cx, cy = self._pet_center()
        x, y = clamp_to_screen(x, y, self.input_bar.width(), self.input_bar.height(), cx, cy)
        self.input_bar.move(x, y)
        self.input_bar.show()
        self.input_bar.raise_()

    def _toggle_popup(self):
        if self.input_bar.isVisible():
            self.input_bar.hide()
        else:
            self._open_input()

    # ---------- 文字发送 ----------
    def _on_send(self, text: str):
        if not self.cfg.get("api_key"):
            self._show_ai_bubble("先设置一下 API Key 哦")
            self.open_settings()
            return
        if self.worker and self.worker.isRunning():
            return
        self.proactive.note_interaction()
        self._idle_timer.stop()  # 新一轮对话开始，暂停空闲隐藏
        if self.tts.is_playing():
            self.tts.stop()
        self._show_user_bubble(text)
        self.engine.set_params(
            api_key=self.cfg.get("api_key"),
            model=self.cfg.get("model"),
            system_prompt=self.cfg.get("system_prompt"),
            base_url=self.cfg.get("llm_base_url", ""),
        )
        self.animator.set_state(Animator.THINKING)
        self._reply_buf = ""
        x, y = self._ai_tail()
        self.ai_bubble.show_text("思考中…", x, y)

        self.worker = ChatWorker(self.engine, text, self.ctx, self)
        self.worker.token_received.connect(self._on_token)
        self.worker.tool_activity.connect(self._on_tool_activity)
        self.worker.confirmRequested.connect(self._on_confirm_requested)
        self.worker.replyFinished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    # ---------- 工具执行 / 确认 ----------
    def _on_tool_activity(self, desc: str):
        x, y = self._ai_tail()
        self.ai_bubble.update_text(f"🛠 {desc}", x, y)
        self.ai_bubble.keep_alive(8000)

    def _on_confirm_requested(self, desc: str):
        self._pending_confirm_worker = self.worker
        if self.confirm_bubble is not None:
            self.confirm_bubble.confirmed.disconnect()
            self.confirm_bubble.close()
            self.confirm_bubble.deleteLater()
        self.confirm_bubble = ConfirmBubble()
        self.confirm_bubble.confirmed.connect(self._on_confirm_resolved)
        x, y = self._ai_tail()
        self.confirm_bubble.ask(desc, x, y)

    def _on_confirm_resolved(self, ok: bool):
        if self._pending_confirm_worker is not None:
            self._pending_confirm_worker.resolve_confirmation(ok)
            self._pending_confirm_worker = None

    def _on_reminder_fire(self, text: str, rid):
        msg = f"⏰ 提醒：{text}"
        self._show_ai_bubble(msg)
        self.animator.play('reminder')
        if self.tray:
            try:
                self.tray.showMessage("小助手的提醒", text, QSystemTrayIcon.Information, 8000)
            except Exception:
                pass
        if self.cfg.get("enable_tts", True):
            self.tts.set_params(api_key=self.cfg.get("api_key"), voice=self.cfg.get("tts_voice", "Cherry"),
                                provider=self.cfg.get("tts_provider", "qwen"),
                                base_url=self.cfg.get("tts_base_url", ""),
                                model=self.cfg.get("tts_model", ""))
            self.tts.speak(f"提醒你，{text}")
        self.proactive.note_interaction()

    def _on_proactive_speak(self, text: str):
        self._show_ai_bubble(text)
        if self.cfg.get("enable_tts", True):
            self.tts.set_params(api_key=self.cfg.get("api_key"), voice=self.cfg.get("tts_voice", "Cherry"),
                                provider=self.cfg.get("tts_provider", "qwen"),
                                base_url=self.cfg.get("tts_base_url", ""),
                                model=self.cfg.get("tts_model", ""))
            self.tts.speak(text)

    def _on_token(self, delta: str):
        self._reply_buf += delta
        self.animator.set_state(Animator.THINKING)
        x, y = self._ai_tail()
        self.ai_bubble.update_text(self._reply_buf, x, y)
        self.ai_bubble.keep_alive(6000)

    def _on_finished(self):
        if self.cfg.get("enable_tts", True) and self._reply_buf.strip():
            self.ai_bubble.keep_alive(60000)
            self.user_bubble.keep_alive(60000)
            self.tts.set_params(
                api_key=self.cfg.get("api_key"),
                voice=self.cfg.get("tts_voice", "Cherry"),
            )
            self.tts.speak(self._reply_buf)
        else:
            self.animator.set_state(Animator.IDLE)
            self._begin_idle_countdown()
        self.worker = None

    def _on_error(self, msg: str):
        self.animator.set_state(Animator.IDLE)
        self._show_ai_bubble("哎呀，出错了 😥")
        self.worker = None
        self._begin_idle_countdown()

    # ---------- 空闲自动隐藏气泡 ----------
    def _on_speak_finished(self):
        self.animator.set_state(Animator.IDLE)
        self._begin_idle_countdown()

    def _begin_idle_countdown(self):
        self.ai_bubble.keep_alive(60000)
        self.user_bubble.keep_alive(60000)
        self._idle_timer.start(IDLE_HIDE_MS)

    def note_user_activity(self):
        if self._idle_timer.isActive():
            self._begin_idle_countdown()

    def _on_idle_timeout(self):
        if self._recording:
            self._begin_idle_countdown()
            return
        if self.confirm_bubble is not None and self.confirm_bubble.isVisible():
            self._begin_idle_countdown()
            return
        if self.input_bar.isVisible() and self.input_bar.edit.hasFocus():
            self._begin_idle_countdown()
            return
        self.ai_bubble.force_fade_out()
        self.user_bubble.force_fade_out()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            self.note_user_activity()
        return super().eventFilter(obj, ev)

    # ---------- 语音输入 ----------
    def _toggle_voice_input(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if not self.cfg.get("api_key"):
            self._show_ai_bubble("先设置一下 API Key 哦")
            self.open_settings()
            return
        if not AudioRecorder.available():
            self._show_ai_bubble("录音不可用")
            return
        self._idle_timer.stop()  # 录音中不自动隐藏
        if self.tts.is_playing():
            self.tts.stop()
        try:
            self.recorder.start()
        except Exception:
            self._show_ai_bubble("麦克风打不开")
            return
        self._recording = True
        self.input_bar.set_voice_active(True)
        self.animator.set_state(Animator.LISTENING)
        x, y = self._ai_tail()
        self.ai_bubble.show_text("🎤 聆听中… 请说话", x, y)
        self._rec_timer.start(MAX_SECONDS * 1000)

    def _stop_recording(self):
        if not self._recording:
            return
        self._recording = False
        self._rec_timer.stop()
        self.input_bar.set_voice_active(False)
        wav = self.recorder.stop_to_wav_bytes()
        dur = self.recorder.duration()
        x, y = self._ai_tail()
        if not wav or dur < 0.4:
            self.animator.set_state(Animator.IDLE)
            self.ai_bubble.show_text("没听清呢 🙉", x, y)
            return
        self.animator.set_state(Animator.THINKING)
        self.ai_bubble.update_text("识别中…", x, y)
        self.asr.set_api_key(self.cfg.get("api_key", ""))
        self.asr_worker = ASRWorker(self.asr, wav, self)
        self.asr_worker.recognized.connect(self._on_recognized)
        self.asr_worker.error.connect(self._on_asr_error)
        self.asr_worker.start()

    def _on_recognized(self, text: str):
        if not text:
            self.animator.set_state(Animator.IDLE)
            self.ai_bubble.update_text("没识别到内容", *self._ai_tail())
            return
        self._on_send(text)

    def _on_asr_error(self, msg: str):
        self.animator.set_state(Animator.IDLE)
        self.ai_bubble.update_text("识别失败了 😢", *self._ai_tail())

    # ---------- 气泡显示辅助 ----------
    def _show_bubble(self, text: str):
        self._show_ai_bubble(text)

    def _show_ai_bubble(self, text: str):
        self._sync_bubble_avoid()
        x, y = self._ai_tail()
        self.ai_bubble.show_text(text, x, y)
        self._begin_idle_countdown()  # 无操作 10 秒后自动消失（期间有操作会重置）

    def _show_user_bubble(self, text: str):
        self._sync_bubble_avoid()
        x, y = self._user_tail()
        self.user_bubble.show_text(text, x, y)

    def _head_top(self) -> QPoint:
        size = int(self.cfg.get("pet_size", 176))
        return QPoint(self._base_pos.x() + size // 2, self._base_pos.y())

    def _ai_tail(self):
        """AI 气泡尾巴锚点（角色右上）"""
        size = int(self.cfg.get("pet_size", 176))
        return (self._base_pos.x() + int(size * 0.62), self._base_pos.y() + 4)

    def _user_tail(self):
        """用户气泡尾巴锚点（角色左上）"""
        size = int(self.cfg.get("pet_size", 176))
        return (self._base_pos.x() + int(size * 0.38), self._base_pos.y() + 4)

    # ---------- 设置 ----------
    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self, memory=self.memory)
        if dlg.exec() == SettingsDialog.Accepted:
            self.cfg = dlg.result_config()
            save_config(self.cfg)
            self._apply_config()

    def _apply_config(self):
        self._update_display()
        self.setWindowOpacity(max(0.4, self.cfg.get("opacity", 255) / 255.0))
        self.tts.set_params(
            voice=self.cfg.get("tts_voice", "Cherry"),
            provider=self.cfg.get("tts_provider", "qwen"),
            base_url=self.cfg.get("tts_base_url", ""),
            model=self.cfg.get("tts_model", ""),
        )
        self.engine.set_params(
            api_key=self.cfg.get("api_key"),
            model=self.cfg.get("model"),
            system_prompt=self.cfg.get("system_prompt"),
            base_url=self.cfg.get("llm_base_url", ""),
        )
        self.ctx["enable_tools"] = self.cfg.get("enable_tools", True)
        self.memory.set_params(
            api_key=self.cfg.get("api_key", ""),
            enabled=bool(self.cfg.get("enable_memory", True)),
            topk=int(self.cfg.get("memory_topk", 4)),
        )
        self.proactive.update_cfg(self.cfg)
        self._apply_topmost_flag()
        self._start_hotkeys()

    # ---------- 热键 ----------
    def _start_hotkeys(self):
        if self.hotkey:
            self.hotkey.stop()
        self.hotkey = HotkeyManager(self.cfg.get("hotkey", "<ctrl>+<shift>+<space>"), self)
        self.hotkey.activated.connect(self._toggle_popup)
        self.hotkey.start()
        if self.voice_hotkey:
            self.voice_hotkey.stop()
            self.voice_hotkey = None
        if self.cfg.get("enable_asr", True):
            self.voice_hotkey = HotkeyManager(self.cfg.get("voice_hotkey", "<ctrl>+<shift>+v"), self)
            self.voice_hotkey.activated.connect(self._toggle_voice_input)
            self.voice_hotkey.start()

    # ---------- 位置持久化 ----------
    def _pos_on_any_screen(self, x, y, w, h) -> bool:
        """检查矩形是否与任一已连接屏幕相交（防止桌宠落在已拔出的幽灵副屏上）"""
        try:
            rect = QRect(x, y, w, h)
            for scr in QApplication.screens():
                if rect.intersects(scr.geometry()):
                    return True
        except Exception:
            pass
        return False

    def _restore_position(self):
        size = int(self.cfg.get("pet_size", 176))
        def primary_pos():
            screen = QApplication.primaryScreen().availableGeometry()
            return (screen.right() - size - 40, screen.bottom() - size - 60)
        if not self.cfg.get("position_set", False):
            x, y = primary_pos()
        else:
            x = self.cfg.get("position_x", 0)
            y = self.cfg.get("position_y", 0)
            x, y = clamp_to_virtual(x, y, size + 20, size + 20)
            # 位置落在已拔出的幽灵屏上：重置到主屏右下角
            if not self._pos_on_any_screen(x, y, size + 20, size + 20):
                x, y = primary_pos()
        self._base_pos = QPoint(x, y)
        self.move(self._base_pos)

    def _save_position(self):
        self.cfg["position_x"] = self._base_pos.x()
        self.cfg["position_y"] = self._base_pos.y()
        self.cfg["position_set"] = True
        save_config(self.cfg)

    # ---------- 退出 ----------
    def _quit(self):
        if self.hotkey:
            self.hotkey.stop()
        if self.voice_hotkey:
            self.voice_hotkey.stop()
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(1000)
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()
