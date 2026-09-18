# -*- coding: utf-8 -*-
"""自检脚本：启动 PetWindow 后 3 秒输出窗口/动画/素材状态，然后退出（供开发验证）"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from ui.pet_window import PetWindow

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
w = PetWindow()
w.show()

def report():
    geo = w.geometry()
    print("PET geo:", geo.x(), geo.y(), geo.width(), geo.height())
    print("PET visible:", w.isVisible())
    print("PET frame:", w._frame is not None, w._frame.width() if w._frame else None, w._frame.height() if w._frame else None)
    print("PET label pixmap null:", w.label.pixmap() is None)
    if w.label.pixmap() is not None:
        print("PET label pixmap size:", w.label.pixmap().width(), w.label.pixmap().height())
    print("Animator state:", w.animator.current_state(), "active:", w.animator.is_active())
    app.quit()

QTimer.singleShot(3000, report)
sys.exit(app.exec())
