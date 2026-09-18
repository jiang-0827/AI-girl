"""主悬浮窗 - 无边框、透明、置顶桌宠；气泡式对话 + 语音/文字输入 + TTS 播报"""
import os
from PyQt5.QtCore import Qt, QPoint, QTimer, QEvent
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import (
    QWidget, QLabel, QMenu, QApplication, QSystemTrayIcon
)

from config import load_config, save_config, get_image_path
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


class PetWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.cfg = load_config()
        self._drag_pos = None
        self._base_pos = QPoint(100, 100)
        self._anim_offset = QPoint(0, 0)
        self._scale = 1.0
        self._blink_on = False
        self._reply_buf = ""
        self._recording = False

        # 角色标签
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)

        # 动画
        self.animator = Animator(self)
        self.animator.offsetChanged.connect(self._on_offset)
        self.animator.scaleChanged.connect(self._on_scale)
        self.animator.blinkChanged.connect(self._on_blink)

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
        self.tts = TTSEngine(self.cfg.get("api_key", ""), self.cfg.get("tts_voice", "Cherry"), self)
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

        # 托盘
        self.tray = None
        self._build_tray()

        self._load_pixmap()
        self._restore_position()
        self.setWindowOpacity(max(0.4, self.cfg.get("opacity", 255) / 255.0))
        self._sync_screen_scale()  # 启动时按所在屏适配大小

        # 热键
        self.hotkey = None
        self.voice_hotkey = None
        self._start_hotkeys()

    # ---------- 渲染 ----------
    def _load_pixmap(self):
        path = get_image_path(self.cfg)
        if not os.path.exists(path):
            path = resource_path("assets/character.png")
        self._pixmap = QPixmap(path)
        # 眨眼帧：与主图同目录的 character_blink.png
        blink_path = os.path.join(os.path.dirname(path), "character_blink.png")
        if not os.path.exists(blink_path):
            blink_path = resource_path("assets/character_blink.png")
        self._blink_pixmap = QPixmap(blink_path) if os.path.exists(blink_path) else QPixmap()
        self._update_pixmap()

    def _update_pixmap(self):
        size = int(self.cfg.get("pet_size", 160))
        w = int(size * self._scale)
        h = int(size * self._scale)
        src = self._pixmap
        if self._blink_on and not self._blink_pixmap.isNull():
            src = self._blink_pixmap
        if not src.isNull():
            scaled = src.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.label.setPixmap(scaled)
        self.resize(size + 20, size + 20)
        self.label.move(10, 10)
        self.label.resize(size, size)

    def _on_offset(self, dx, dy):
        self._anim_offset = QPoint(dx, dy)
        self.move(self._base_pos + self._anim_offset)
        self._reposition_bubbles()

    def _on_scale(self, s):
        self._scale = s
        self._update_pixmap()

    def _on_blink(self, on):
        self._blink_on = on
        self._update_pixmap()

    def _reposition_bubbles(self):
        if self.ai_bubble.isVisible():
            x, y = self._ai_tail()
            self.ai_bubble.update_text(self.ai_bubble._text, x, y)
        if self.user_bubble.isVisible():
            x, y = self._user_tail()
            self.user_bubble.update_text(self.user_bubble._text, x, y)

    def _pet_center(self):
        size = int(self.cfg.get("pet_size", 160))
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
        # 尺寸变化后重新定位，保证不超出当前屏
        self._reposition_bubbles()
        if self.input_bar.isVisible():
            self._open_input()

    # ---------- 拖拽 ----------
    def mousePressEvent(self, ev):
        self.note_user_activity()
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPos() - self._base_pos
        elif ev.button() == Qt.RightButton:
            self._show_menu(ev.globalPos())

    def mouseMoveEvent(self, ev):
        if self._drag_pos is not None:
            self._base_pos = ev.globalPos() - self._drag_pos
            self.move(self._base_pos + self._anim_offset)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._drag_pos is not None:
            # 几乎没移动 -> 视为点击，打开输入条
            moved = (ev.globalPos() - self._drag_pos) - self._base_pos
            if abs(moved.x()) < 3 and abs(moved.y()) < 3:
                self._open_input()
            self._drag_pos = None
            self._save_position()
            self._sync_screen_scale()  # 可能换到了另一块屏，重算大小

    # ---------- 菜单 ----------
    def _show_menu(self, global_pos):
        menu = QMenu()
        act_chat = menu.addAction("聊天")
        act_voice = menu.addAction("语音说话")
        act_settings = menu.addAction("设置")
        act_reset = menu.addAction("重置对话")
        act_hide = menu.addAction("隐藏")
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        chosen = menu.exec_(global_pos)
        if chosen == act_chat:
            self._open_input()
        elif chosen == act_voice:
            self._toggle_voice_input()
        elif chosen == act_settings:
            self.open_settings()
        elif chosen == act_reset:
            self.engine.reset()
            self._show_ai_bubble("对话已重置～")
        elif chosen == act_hide:
            self.hide()
        elif chosen == act_quit:
            self._quit()

    # ---------- 托盘 ----------
    def _build_tray(self):
        icon_path = resource_path("assets/tray_icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.setWindowIcon(icon)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon, self)
            menu = QMenu()
            menu.addAction("显示/隐藏", self._toggle_visible)
            menu.addAction("设置", self.open_settings)
            menu.addSeparator()
            menu.addAction("退出", self._quit)
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
        size = int(self.cfg.get("pet_size", 160))
        x = self._base_pos.x() + size // 2 - self.input_bar.width() // 2
        y = self._base_pos.y() + size + 16
        # 以角色所在屏幕为边界，使输入条跟随角色到副屏且完整显示在该屏
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
        # 由 worker 线程发出，转主线程处理；每次新建一个确认气泡，避免复用顶层窗口弹不出
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
        if self.tray:
            try:
                self.tray.showMessage("小助手的提醒", text, QSystemTrayIcon.Information, 8000)
            except Exception:
                pass
        if self.cfg.get("enable_tts", True):
            self.tts.set_params(api_key=self.cfg.get("api_key"), voice=self.cfg.get("tts_voice", "Cherry"))
            self.tts.speak(f"提醒你，{text}")
        self.proactive.note_interaction()

    def _on_proactive_speak(self, text: str):
        self._show_ai_bubble(text)
        if self.cfg.get("enable_tts", True):
            self.tts.set_params(api_key=self.cfg.get("api_key"), voice=self.cfg.get("tts_voice", "Cherry"))
            self.tts.speak(text)

    def _on_token(self, delta: str):
        self._reply_buf += delta
        self.animator.set_state(Animator.THINKING)
        x, y = self._ai_tail()
        self.ai_bubble.update_text(self._reply_buf, x, y)
        self.ai_bubble.keep_alive(6000)

    def _on_finished(self):
        if self.cfg.get("enable_tts", True) and self._reply_buf.strip():
            # 播报期间保持气泡不自动淡出，倒计时等 speakFinished 后启动
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
        """本轮对话结束：把气泡自身定时淡出让位于空闲计时器，避免两套计时冲突。"""
        self.ai_bubble.keep_alive(60000)
        self.user_bubble.keep_alive(60000)
        self._idle_timer.start(IDLE_HIDE_MS)

    def note_user_activity(self):
        """任一用户交互：若空闲倒计时在跑则重新计时。"""
        if self._idle_timer.isActive():
            self._begin_idle_countdown()

    def _on_idle_timeout(self):
        # 正在录音 / 确认弹窗在前台 / 用户正在输入 → 不误隐藏，重新计时
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
        # 监听本应用内的键盘/鼠标/滚轮活动，用于重置空闲计时
        t = ev.type()
        if t in (QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.Wheel):
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
        except Exception as e:
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
        # 识别到的话作为用户输入，走同样的对话流程
        self._on_send(text)

    def _on_asr_error(self, msg: str):
        self.animator.set_state(Animator.IDLE)
        self.ai_bubble.update_text("识别失败了 😢", *self._ai_tail())

    # ---------- 气泡显示辅助 ----------
    def _show_bubble(self, text: str):
        self._show_ai_bubble(text)

    def _show_ai_bubble(self, text: str):
        x, y = self._ai_tail()
        self.ai_bubble.show_text(text, x, y)

    def _show_user_bubble(self, text: str):
        x, y = self._user_tail()
        self.user_bubble.show_text(text, x, y)

    def _head_top(self) -> QPoint:
        size = int(self.cfg.get("pet_size", 160))
        return QPoint(self._base_pos.x() + size // 2, self._base_pos.y())

    def _ai_tail(self):
        """AI 气泡尾巴锚点（角色右上）"""
        size = int(self.cfg.get("pet_size", 160))
        return (self._base_pos.x() + int(size * 0.62), self._base_pos.y() + 4)

    def _user_tail(self):
        """用户气泡尾巴锚点（角色左上）"""
        size = int(self.cfg.get("pet_size", 160))
        return (self._base_pos.x() + int(size * 0.38), self._base_pos.y() + 4)

    # ---------- 设置 ----------
    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self, memory=self.memory)
        if dlg.exec_() == SettingsDialog.Accepted:
            self.cfg = dlg.result_config()
            save_config(self.cfg)
            self._apply_config()

    def _apply_config(self):
        self._load_pixmap()
        self.setWindowOpacity(max(0.4, self.cfg.get("opacity", 255) / 255.0))
        self.tts.set_params(voice=self.cfg.get("tts_voice", "Cherry"))
        self.ctx["enable_tools"] = self.cfg.get("enable_tools", True)
        self.memory.set_params(
            api_key=self.cfg.get("api_key", ""),
            enabled=bool(self.cfg.get("enable_memory", True)),
            topk=int(self.cfg.get("memory_topk", 4)),
        )
        self.proactive.update_cfg(self.cfg)
        self._start_hotkeys()

    # ---------- 热键 ----------
    def _start_hotkeys(self):
        # 聊天输入热键
        if self.hotkey:
            self.hotkey.stop()
        self.hotkey = HotkeyManager(self.cfg.get("hotkey", "<ctrl>+<shift>+<space>"), self)
        self.hotkey.activated.connect(self._toggle_popup)
        self.hotkey.start()
        # 语音输入热键
        if self.voice_hotkey:
            self.voice_hotkey.stop()
            self.voice_hotkey = None
        if self.cfg.get("enable_asr", True):
            self.voice_hotkey = HotkeyManager(self.cfg.get("voice_hotkey", "<ctrl>+<shift>+v"), self)
            self.voice_hotkey.activated.connect(self._toggle_voice_input)
            self.voice_hotkey.start()

    # ---------- 位置持久化 ----------
    def _restore_position(self):
        size = int(self.cfg.get("pet_size", 160))
        if not self.cfg.get("position_set", False):
            # 从未设置过：默认放在主屏右下角
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.right() - size - 40
            y = screen.bottom() - size - 60
        else:
            x = self.cfg.get("position_x", 0)
            y = self.cfg.get("position_y", 0)
            # 用整个虚拟桌面做包含（允许负坐标），防止显示器变更后遗留在屏外
            x, y = clamp_to_virtual(x, y, size + 20, size + 20)
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
