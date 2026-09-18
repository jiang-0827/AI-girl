"""确认气泡 - 需要用户批准的危险/系统操作时弹出，带 确认/取消 按钮"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)


class ConfirmBubble(QWidget):
    """显示一条待确认操作 + 确认/取消按钮"""
    confirmed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(300)

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)

        panel = QWidget(self)
        panel.setObjectName("panel")
        panel.setStyleSheet("""
            #panel { background: rgba(40, 30, 46, 245); border-radius: 14px;
                     border: 1px solid #ffb347; }
            QLabel#title { color: #ffcf87; font-weight: bold; }
            QLabel#desc { color: #f0eaf0; }
            QPushButton { border: none; border-radius: 9px; padding: 7px 0;
                          font-weight: bold; font-size: 13px; }
            QPushButton#ok { background: #ff7a7a; color: white; }
            QPushButton#ok:hover { background: #ff5c5c; }
            QPushButton#no { background: #4a5568; color: #e6ebf5; }
            QPushButton#no:hover { background: #5a6578; }
        """)
        v.addWidget(panel)

        pv = QVBoxLayout(panel)
        pv.setContentsMargins(14, 12, 14, 12)
        pv.setSpacing(8)

        title = QLabel("⚠ 请确认操作")
        title.setObjectName("title")
        title.setFont(QFont("Microsoft YaHei", 11))
        pv.addWidget(title)

        self.desc = QLabel("")
        self.desc.setObjectName("desc")
        self.desc.setFont(QFont("Microsoft YaHei", 10))
        self.desc.setWordWrap(True)
        pv.addWidget(self.desc)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_no = QPushButton("取消")
        self.btn_no.setObjectName("no")
        self.btn_ok = QPushButton("确认执行")
        self.btn_ok.setObjectName("ok")
        self.btn_no.clicked.connect(lambda: self._resolve(False))
        self.btn_ok.clicked.connect(lambda: self._resolve(True))
        row.addWidget(self.btn_no)
        row.addWidget(self.btn_ok)
        pv.addLayout(row)

    def ask(self, desc, anchor_x, anchor_y):
        self.desc.setText(f"我准备「{desc}」，是否允许？")
        self.adjustSize()
        x = anchor_x - self.width() // 2
        y = anchor_y - self.height() - 6
        screen = QApplication_geometry()
        x = max(0, min(x, screen[0] - self.width()))
        y = max(0, y)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.btn_ok.setFocus(Qt.OtherFocusReason)

    def _resolve(self, ok):
        self.hide()
        self.confirmed.emit(ok)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._resolve(True)
        elif ev.key() == Qt.Key_Escape:
            self._resolve(False)
        else:
            super().keyPressEvent(ev)


def QApplication_geometry():
    from PyQt5.QtWidgets import QApplication
    g = QApplication.primaryScreen().availableGeometry()
    return (g.width(), g.height())
