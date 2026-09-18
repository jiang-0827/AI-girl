"""极简输入条 - 悬浮在角色下方的一行输入，含 发送 / 语音 / 取消 按钮"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QGraphicsDropShadowEffect
)


class InputBar(QWidget):
    """轻量输入气泡条，不是聊天面板，仅一行输入 + 三个按钮"""
    sendRequested = pyqtSignal(str)
    voiceToggled = pyqtSignal()

    # 基准尺寸（主屏 100% 缩放时）
    BASE_HEIGHT = 52
    BASE_EDIT_W = 240

    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._scale = 1.0
        self.setFixedHeight(self.BASE_HEIGHT)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)

        bar = QWidget(self)
        bar.setObjectName("bar")
        bar.setStyleSheet("""
            #bar { background: rgba(38, 44, 60, 235); border-radius: 22px; }
            QLineEdit {
                background: transparent; border: none; color: #eef2fb;
                padding: 0 10px; font-size: 14px;
            }
            QPushButton#btn {
                background: transparent; border: none; color: #cdd6f4;
                font-size: 18px; padding: 0 6px;
            }
            QPushButton#btn:hover { color: #ffffff; }
            QPushButton#send {
                background: #6aa9ff; border: none; color: white;
                border-radius: 16px; padding: 0 14px; font-size: 15px; font-weight: bold;
            }
            QPushButton#send:hover { background: #5694f0; }
        """)
        shadow = QGraphicsDropShadowEffect(bar)
        shadow.setBlurRadius(24)
        shadow.setColor(Qt.darkGray)
        shadow.setOffset(0, 3)
        bar.setGraphicsEffect(shadow)
        outer.addWidget(bar)

        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(4)

        self.btn_voice = QPushButton("🎤")
        self.btn_voice.setObjectName("btn")
        self.btn_voice.setCheckable(True)
        self.btn_voice.setToolTip("语音输入（Ctrl+Shift+V）")
        self.btn_voice.clicked.connect(self.voiceToggled)
        row.addWidget(self.btn_voice)

        self.edit = QLineEdit(bar)
        self.edit.setFont(QFont("Microsoft YaHei", 11))
        self.edit.setPlaceholderText("说点什么…  Enter 发送 / Esc 取消")
        self.edit.setMinimumWidth(240)
        self.edit.installEventFilter(self)
        row.addWidget(self.edit, 1)

        self.btn_send = QPushButton("发送")
        self.btn_send.setObjectName("send")
        self.btn_send.setFixedHeight(32)
        self.btn_send.clicked.connect(self._do_send)
        row.addWidget(self.btn_send)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("btn")
        self.btn_close.setToolTip("取消 / 关闭")
        self.btn_close.clicked.connect(self.hide)
        row.addWidget(self.btn_close)

        self.adjustSize()
        self.edit.textChanged.connect(lambda _: self.adjustSize())

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == ev.KeyPress:
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._do_send()
                return True
            if ev.key() == Qt.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, ev)

    def _do_send(self):
        text = self.edit.text().strip()
        if not text:
            return
        self.edit.clear()
        self.sendRequested.emit(text)

    def set_voice_active(self, active: bool):
        self.btn_voice.setChecked(active)
        self.btn_voice.setText("🔴" if active else "🎤")

    def apply_scale(self, factor: float):
        """根据屏幕缩放因子调整高度/字号/宽度，用于主副屏切换。"""
        factor = max(0.6, min(1.6, float(factor)))
        if abs(factor - self._scale) < 0.01:
            return
        self._scale = factor
        self.setFixedHeight(round(self.BASE_HEIGHT * factor))
        self.edit.setMinimumWidth(round(self.BASE_EDIT_W * factor))
        fs = lambda base: max(10, round(base * factor))
        # 用字体对象缩放更可靠
        f = self.edit.font()
        f.setPixelSize(fs(14))
        self.edit.setFont(f)
        sf = self.btn_send.font()
        sf.setPixelSize(fs(15))
        self.btn_send.setFont(sf)
        self.btn_send.setFixedHeight(round(32 * factor))
        for b in (self.btn_voice, self.btn_close):
            bf = b.font()
            bf.setPixelSize(fs(18))
            b.setFont(bf)
        self.adjustSize()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(ev)

    def showEvent(self, ev):
        self.edit.setFocus()
        super().showEvent(ev)
