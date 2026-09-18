"""对话气泡 - 指向角色的漫画式气泡，支持 user / ai 两种角色样式"""
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QRect
from PyQt5.QtGui import QPainter, QColor, QFont, QPainterPath, QFontMetrics
from PyQt5.QtWidgets import QWidget, QGraphicsOpacityEffect


class ChatBubble(QWidget):
    """无边框置顶气泡，圆角矩形 + 底部小三角指向角色"""

    MAX_WIDTH = 300

    def __init__(self, role: str = "ai", align: str = "center", parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.role = role          # 'ai' 或 'user'
        self.align = align        # 尾巴位置: 'left' / 'center' / 'right'

        self._text = ""
        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._start_fade_out)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(300)
        self._anim.finished.connect(self._maybe_hide)

        self._font = QFont("Microsoft YaHei", 11)

    # ---------- 对外接口 ----------
    def show_text(self, text: str, tail_x: int, tail_y: int):
        self._text = text
        self._relayout()
        self._position(tail_x, tail_y)
        self.show()
        self._fade_in()

    def update_text(self, text: str, tail_x: int = None, tail_y: int = None):
        self._text = text
        self._relayout()
        if tail_x is not None:
            self._position(tail_x, tail_y)
        self._fade_timer.start(3000)

    def keep_alive(self, ms: int = 6000):
        self._fade_timer.start(ms)

    def _position(self, tail_x, tail_y):
        # 根据尾巴对齐方式决定气泡横向位置
        if self.align == 'left':
            x = tail_x - 24
        elif self.align == 'right':
            x = tail_x - self.width() + 24
        else:
            x = tail_x - self.width() // 2
        y = tail_y - self.height()
        self.move(max(0, int(x)), max(0, int(y)))

    # ---------- 布局 ----------
    def _relayout(self):
        lines = self._wrap(self._text)
        line_h = 24
        w = min(self.MAX_WIDTH, max(80, self._max_line_width(lines) + 36))
        h = len(lines) * line_h + 40
        self.setFixedSize(int(w), int(h))

    def _wrap(self, text):
        chars_per = max(6, (self.MAX_WIDTH - 36) // 22)
        out, cur = [], ""
        for ch in text:
            cur += ch
            if len(cur) >= chars_per:
                out.append(cur)
                cur = ""
        if cur:
            out.append(cur)
        return out or [""]

    def _max_line_width(self, lines):
        fm = QFontMetrics(self._font)
        return max((fm.horizontalAdvance(l) for l in lines), default=40)

    # ---------- 淡入淡出 ----------
    def _fade_in(self):
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self.keep_alive(6000)

    def _start_fade_out(self):
        self._anim.stop()
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _maybe_hide(self):
        if self._opacity.opacity() < 0.05:
            self.hide()

    # ---------- 绘制 ----------
    def paintEvent(self, ev):
        if not self._text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        body_h = h - 16

        if self.role == 'user':
            fill = QColor(108, 178, 255, 240)
            pen_color = QColor(255, 255, 255)
        else:
            fill = QColor(255, 255, 255, 242)
            pen_color = QColor(45, 45, 55)

        # 尾巴横向位置
        if self.align == 'left':
            cx = 24
        elif self.align == 'right':
            cx = w - 24
        else:
            cx = w // 2

        path = QPainterPath()
        path.addRoundedRect(2, 2, w - 4, body_h - 4, 14, 14)
        path.moveTo(cx - 9, body_h - 4)
        path.lineTo(cx, h - 2)
        path.lineTo(cx + 9, body_h - 4)
        path.closeSubpath()

        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(path)

        p.setPen(pen_color)
        p.setFont(self._font)
        text_rect = QRect(18, 12, w - 36, body_h - 24)
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self._text)
        p.end()
