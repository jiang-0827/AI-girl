"""角色动画控制器 - 待机浮动、说话、思考效果"""
import math
import random
from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class Animator(QObject):
    """通过定时器驱动，发出偏移/缩放信号供窗口应用"""
    offsetChanged = pyqtSignal(int, int)   # (dx, dy) 像素偏移
    scaleChanged = pyqtSignal(float)       # 缩放系数
    blinkChanged = pyqtSignal(bool)        # 眨眼：True=闭眼

    IDLE = 'idle'
    TALKING = 'talking'
    THINKING = 'thinking'
    LISTENING = 'listening'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t = 0.0
        self._state = self.IDLE
        self._blink_on = False
        self._blink_until = 0.0
        self._next_blink = random.uniform(2.0, 4.0)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30fps

    def set_state(self, state: str):
        self._state = state

    def _tick(self):
        self._t += 0.033
        if self._state == self.IDLE:
            # 缓慢正弦浮动，振幅 4px，周期约 2.4s
            dy = int(round(4 * math.sin(self._t * 2.6)))
            self.offsetChanged.emit(0, dy)
            self.scaleChanged.emit(1.0)
        elif self._state == self.TALKING:
            # 快速浮动 + 轻微缩放脉动
            dy = int(round(6 * math.sin(self._t * 7.0)))
            scale = 1.0 + 0.03 * math.sin(self._t * 7.0)
            self.offsetChanged.emit(0, dy)
            self.scaleChanged.emit(scale)
        elif self._state == self.THINKING:
            # 左右摇摆
            dx = int(round(5 * math.sin(self._t * 5.0)))
            self.offsetChanged.emit(dx, 0)
            self.scaleChanged.emit(1.0)
        elif self._state == self.LISTENING:
            # 录音时：轻微放大脉动 + 上下浮动，表示在听
            dy = int(round(3 * math.sin(self._t * 4.0)))
            scale = 1.05 + 0.04 * math.sin(self._t * 4.0)
            self.offsetChanged.emit(0, dy)
            self.scaleChanged.emit(scale)
        self._update_blink()

    def _update_blink(self):
        if not self._blink_on and self._t >= self._next_blink:
            self._blink_on = True
            self._blink_until = self._t + random.uniform(0.11, 0.16)
            self.blinkChanged.emit(True)
        elif self._blink_on and self._t >= self._blink_until:
            self._blink_on = False
            # 偶尔连眨两次，否则随机间隔 2.5~5.5 秒
            if random.random() < 0.25:
                self._next_blink = self._t + random.uniform(0.14, 0.22)
            else:
                self._next_blink = self._t + random.uniform(2.5, 5.5)
            self.blinkChanged.emit(False)
