"""主动关怀引擎 - 空闲问候 / 整点报时 / 久坐提醒，通过回调触发主动播报"""
import time
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

IDLE_GREETINGS = [
    "忙了挺久啦，要不要休息一下？",
    "我一直都在哦，需要我帮你做点什么吗？",
    "喝口水吧，别老盯着屏幕～",
    "有什么想聊的，随时叫我。",
]


class ProactiveEngine(QObject):
    """定期检查是否该主动说话，发出 speakRequested 信号"""
    speakRequested = pyqtSignal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.last_interaction = time.time()
        self.last_hour = time.localtime().tm_hour
        self.last_break_remind = time.time()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30 * 1000)  # 每 30 秒检查一次

    def note_interaction(self):
        self.last_interaction = time.time()

    def update_cfg(self, cfg):
        self.cfg = cfg

    def _tick(self):
        now = time.time()
        lt = time.localtime(now)

        # 整点报时（可选）
        if self.cfg.get("proactive_hourly", False) and lt.tm_hour != self.last_hour and lt.tm_min == 0:
            self.last_hour = lt.tm_hour
            self.speakRequested.emit(f"已经 {lt.tm_hour} 点整啦。")
            return

        # 空闲主动关怀
        idle_min = self.cfg.get("proactive_idle_min", 30)
        if self.cfg.get("proactive_enabled", True) and (now - self.last_interaction) >= idle_min * 60:
            import random
            self.speakRequested.emit(random.choice(IDLE_GREETINGS))
            self.last_interaction = now  # 重置，避免连续打扰
            return

        # 久坐提醒
        sed_min = self.cfg.get("proactive_sit_min", 60)
        if self.cfg.get("proactive_sit_enabled", False) and (now - self.last_break_remind) >= sed_min * 60:
            self.last_break_remind = now
            self.speakRequested.emit("坐了一个多小时啦，起来活动活动吧！")
