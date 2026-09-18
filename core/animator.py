"""角色动画状态机 - 多帧 PNG 动画播放（素材来自桌宠素材管线 13 状态 68 帧）

- 基态语义（AI 对话）：idle / talking(chat帧) / thinking / listening
- 互动动画（优先抢占）：jump / shake / run-left / run-right / pet-head / feed /
  walk / coffee / sleep / reminder / blink / squash
- 优先级：高优先级可打断低优先级；一次性动画播完 / 限时循环到期后恢复基态
"""
import os
import math
import random
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QPixmap
from utils.resource_path import resource_path

ANIM_DIR = "assets/anim"
TICK_MS = 16  # ~60fps 主循环


class Animator(QObject):
    frameChanged = Signal(object)     # QPixmap 当前帧
    offsetChanged = Signal(int, int)  # (dx, dy)
    scaleChanged = Signal(float)      # 缩放系数

    # 基态语义
    IDLE = 'idle'
    TALKING = 'talking'
    THINKING = 'thinking'
    LISTENING = 'listening'

    # 动画状态定义：frames 帧数 / ms 单帧时长 / loop 是否循环 /
    # priority 抢占优先级 / duration_ms 限时(循环动画) / once 一次性
    STATES = {
        'idle':      dict(frames=4, ms=900,  loop=True,  priority=10, once=False),
        'sit':       dict(frames=4, ms=700,  loop=True,  priority=15, once=False, duration_ms=9000),
        'blink':     dict(frames=5, ms=75,   loop=False, priority=30, once=True),
        'chat':      dict(frames=5, ms=140,  loop=True,  priority=85, once=False),
        'jump':      dict(frames=5, ms=110,  loop=False, priority=70, once=True),
        'shake':     dict(frames=5, ms=80,   loop=False, priority=60, once=True),
        'run-left':  dict(frames=6, ms=90,   loop=True,  priority=90, once=False),
        'run-right': dict(frames=6, ms=90,   loop=True,  priority=90, once=False),
        'pet-head':  dict(frames=5, ms=130,  loop=True,  priority=85, once=False, duration_ms=2200),
        'feed':      dict(frames=5, ms=130,  loop=True,  priority=85, once=False, duration_ms=2600),
        'walk':      dict(frames=6, ms=160,  loop=True,  priority=85, once=False, duration_ms=10000),
        'coffee':    dict(frames=5, ms=130,  loop=True,  priority=85, once=False, duration_ms=2800),
        'sleep':     dict(frames=5, ms=220,  loop=True,  priority=85, once=False, duration_ms=8000),
        'reminder':  dict(frames=5, ms=140,  loop=False, priority=95, once=True),
    }

    # 基态语义 -> 实际动画帧（thinking/listening 复用 idle 帧，靠 offset/scale 区分）
    BASE_MAP = {
        IDLE: 'idle',
        TALKING: 'chat',
        THINKING: 'idle',
        LISTENING: 'idle',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmaps = {}      # prefix -> [QPixmap...]
        self._base = self.IDLE
        self._active = None     # (name, elapsed_ms) 正在播放的互动动画
        self._idx = 0
        self._frame_elapsed = 0.0
        self._t = 0.0
        self._next_blink_at = random.uniform(2.5, 5.5)
        self._squash = None     # (elapsed_ms, duration_ms) 压扁回弹
        self._cur_frame = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    # ---------- 对外接口 ----------
    def set_state(self, state: str):
        """设置基态（idle/talking/thinking/listening），无互动动画时立即生效。"""
        if state not in self.BASE_MAP:
            state = self.IDLE
        self._base = state
        if self._active is None:
            self._idx = 0
            self._frame_elapsed = 0.0
            self._emit_now()

    def play(self, name: str):
        """播放互动动画。高优先级打断低优先级；低优先级请求被忽略。"""
        if name not in self.STATES:
            return
        st = self.STATES[name]
        cur_pri = self.STATES[self._active[0]]['priority'] if self._active else 0
        if self._active and st['priority'] < cur_pri:
            return
        self._active = (name, 0.0)
        self._idx = 0
        self._frame_elapsed = 0.0
        self._emit_now()

    def stop_active(self):
        """立即结束互动动画，恢复基态（如拖拽结束）。"""
        if self._active is not None:
            self._active = None
            self._idx = 0
            self._frame_elapsed = 0.0
            self._emit_now()

    def play_squash(self):
        """压扁回弹（点击互动用）：320ms 内 压扁→回弹→稳定。"""
        self._squash = (0.0, 320.0)

    def is_active(self) -> bool:
        return self._active is not None

    def current_state(self) -> str:
        return self._active[0] if self._active else self.BASE_MAP[self._base]

    # ---------- 帧加载 ----------
    def _load(self, prefix: str):
        if prefix in self._pixmaps:
            return self._pixmaps[prefix]
        frames = []
        n = self.STATES[prefix]['frames']
        for i in range(1, n + 1):
            path = resource_path(os.path.join(ANIM_DIR, f"{prefix}-{i:02d}.png"))
            pm = QPixmap(path)
            frames.append(pm)
        self._pixmaps[prefix] = frames
        return frames

    # ---------- 主循环 ----------
    def _tick(self):
        dt = TICK_MS / 1000.0
        self._t += dt

        # 1) 压扁回弹 scale
        if self._squash is not None:
            el, dur = self._squash
            el += dt * 1000
            self._squash = (el, dur)
            self.scaleChanged.emit(self._squash_scale(el))
            if el >= dur:
                self._squash = None

        # 2) 动画帧推进
        name = self._active[0] if self._active else self.BASE_MAP[self._base]
        st = self.STATES[name]

        if self._active is not None:
            active_el = self._active[1] + dt * 1000
            dur = st.get('duration_ms')
            if dur is not None and active_el >= dur:
                # 限时循环动画到期 -> 恢复基态
                self._active = None
                self._idx = 0
                self._frame_elapsed = 0.0
                name = self.BASE_MAP[self._base]
                st = self.STATES[name]
            else:
                self._active = (name, active_el)
        else:
            # 基态下随机眨眼（仅 idle 时触发）
            if self._base == self.IDLE and self._t >= self._next_blink_at:
                self._active = ('blink', 0.0)
                self._idx = 0
                self._frame_elapsed = 0.0
                self._next_blink_at = self._t + random.uniform(2.5, 5.5)

        # 帧推进
        frames = self._load(name)
        self._frame_elapsed += dt * 1000
        guard = 0
        while self._frame_elapsed >= st['ms'] and frames and guard < 100:
            guard += 1
            self._frame_elapsed -= st['ms']
            self._idx += 1
            if self._idx >= len(frames):
                if st['once']:
                    # 一次性动画播完 -> 恢复基态
                    if self._active is not None:
                        self._active = None
                    self._idx = 0
                    name = self.BASE_MAP[self._base]
                    st = self.STATES[name]
                    frames = self._load(name)
                    break
                self._idx = 0
                if not st['loop']:
                    break
        if frames:
            self._cur_frame = frames[self._idx % len(frames)]
            self.frameChanged.emit(self._cur_frame)

        # 3) 基态 offset/scale 效果（互动动画时若有 squash 已单独发过 scale）
        if self._squash is None:
            self._emit_motion(name)

    def _emit_motion(self, name):
        if name == 'chat':
            dy = int(round(6 * math.sin(self._t * 7.0)))
            s = 1.0 + 0.03 * math.sin(self._t * 7.0)
            self.offsetChanged.emit(0, dy)
            self.scaleChanged.emit(s)
        elif name == 'thinking':
            dx = int(round(5 * math.sin(self._t * 5.0)))
            self.offsetChanged.emit(dx, 0)
            self.scaleChanged.emit(1.0)
        elif name == 'listening':
            dy = int(round(3 * math.sin(self._t * 4.0)))
            s = 1.05 + 0.04 * math.sin(self._t * 4.0)
            self.offsetChanged.emit(0, dy)
            self.scaleChanged.emit(s)
        else:
            # idle 及互动动画：轻微呼吸浮动
            dy = int(round(4 * math.sin(self._t * 2.6)))
            self.offsetChanged.emit(0, dy)
            self.scaleChanged.emit(1.0)

    def _emit_now(self):
        name = self._active[0] if self._active else self.BASE_MAP[self._base]
        frames = self._load(name)
        if frames:
            self._cur_frame = frames[self._idx % len(frames)]
            self.frameChanged.emit(self._cur_frame)
        self._emit_motion(name)

    def _squash_scale(self, el):
        # 0-100ms 压扁 1.0→0.90；100-180ms 回弹 0.90→1.06；180-260ms 回落 1.06→1.0；之后稳定
        if el < 100:
            return 1.0 - 0.10 * (el / 100.0)
        if el < 180:
            return 0.90 + 0.16 * ((el - 100) / 80.0)
        if el < 260:
            return 1.06 - 0.06 * ((el - 180) / 80.0)
        return 1.0
