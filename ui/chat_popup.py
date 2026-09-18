"""聊天输入弹窗 - 半透明磨砂背景，含对话历史和输入框（基于消息列表模型渲染）"""
from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel
)


class ChatPopup(QWidget):
    """聊天窗口：显示对话历史 + 输入发送"""
    sendRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(360, 320)

        # 消息存储：[{"role": "user"/"ai", "text": ...}]
        self._messages = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        panel = QWidget(self)
        panel.setObjectName("chatPanel")
        panel.setStyleSheet("""
            #chatPanel {
                background: rgba(30, 34, 48, 225);
                border-radius: 14px;
            }
            QTextEdit#history {
                background: transparent; border: none; color: #eaeefb;
            }
            QTextEdit#input {
                background: rgba(255,255,255,235); border: none; border-radius: 8px;
                padding: 6px 8px; color: #222;
            }
            QPushButton {
                background: #6aa9ff; color: white; border: none;
                border-radius: 8px; padding: 6px 14px; font-weight: bold;
            }
            QPushButton:hover { background: #5694f0; }
            QLabel#title { color: #cdd6f4; font-weight: bold; }
        """)
        outer.addWidget(panel)

        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        title = QLabel("🤖 和小助手聊聊")
        title.setObjectName("title")
        title.setFont(QFont("Microsoft YaHei", 11))
        v.addWidget(title)

        self.history = QTextEdit(panel)
        self.history.setObjectName("history")
        self.history.setReadOnly(True)
        self.history.setFont(QFont("Microsoft YaHei", 10))
        v.addWidget(self.history, 1)

        row = QHBoxLayout()
        self.input = QTextEdit(panel)
        self.input.setObjectName("input")
        self.input.setFont(QFont("Microsoft YaHei", 10))
        self.input.setFixedHeight(50)
        self.input.setPlaceholderText("输入消息，Enter 发送，Shift+Enter 换行，Esc 关闭")
        row.addWidget(self.input, 1)

        self.btn_send = QPushButton("发送")
        self.btn_send.setFixedWidth(64)
        self.btn_send.clicked.connect(self._do_send)
        row.addWidget(self.btn_send, 0, Qt.AlignBottom)
        v.addLayout(row)

        self.input.installEventFilter(self)

    # ---- 事件处理 ----
    def eventFilter(self, obj, ev):
        if obj is self.input and ev.type() == QEvent.Type.KeyPress:
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and not (ev.modifiers() & Qt.ShiftModifier):
                self._do_send()
                return True
            if ev.key() == Qt.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(ev)

    def closeEvent(self, ev):
        ev.ignore()
        self.hide()

    # ---- 发送 ----
    def _do_send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self._messages.append({"role": "user", "text": text})
        self._render()
        self.sendRequested.emit(text)

    def submit(self, text: str):
        """供外部（语音输入）直接提交一条用户消息"""
        text = text.strip()
        if not text:
            return
        self._messages.append({"role": "user", "text": text})
        self._render()
        self.sendRequested.emit(text)

    # ---- 消息追加接口 ----
    def begin_ai_message(self):
        self._messages.append({"role": "ai", "text": ""})
        self._render()

    def append_ai_delta(self, delta: str):
        if self._messages and self._messages[-1]["role"] == "ai":
            self._messages[-1]["text"] += delta
            self._render()

    def set_ai_full(self, text: str):
        if self._messages and self._messages[-1]["role"] == "ai":
            self._messages[-1]["text"] = text
        else:
            self._messages.append({"role": "ai", "text": text})
        self._render()

    def append_error(self, text: str):
        self._messages.append({"role": "err", "text": text})
        self._render()

    # ---- 渲染 ----
    def _render(self):
        parts = []
        for m in self._messages:
            role = m["role"]
            body = self._esc(m["text"])
            if role == "user":
                parts.append(f'<div style="margin:4px 0;"><span style="color:#8bd3ff;font-weight:bold;">我：</span>{body}</div>')
            elif role == "ai":
                parts.append(f'<div style="margin:4px 0;"><span style="color:#ffe08a;font-weight:bold;">助手：</span>{body}</div>')
            elif role == "err":
                parts.append(f'<div style="margin:4px 0;"><span style="color:#ff8a8a;">⚠ {body}</span></div>')
        self.history.setHtml("".join(parts))
        sb = self.history.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _esc(self, s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace("\n", "<br>"))
