# -*- coding: utf-8 -*-
"""验证脚本：启动桌宠 → 播放坐姿动画 → 截取窗口画面 → 恢复站姿 → 截图 → 退出"""
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

def shot_sit():
    w.animator.play('sit')
    print("SIT state:", w.animator.current_state())
    QTimer.singleShot(2500, grab_sit)

def grab_sit():
    pm = w.grab()
    pm.save(r'E:\DesktopPetAI\sit-shot.png')
    print("sit-shot saved", pm.width(), pm.height())
    w.animator.set_state('idle')
    w.animator.stop_active()
    QTimer.singleShot(1500, grab_idle)

def grab_idle():
    pm = w.grab()
    pm.save(r'E:\DesktopPetAI\idle-shot.png')
    print("idle-shot saved", pm.width(), pm.height())
    app.quit()

QTimer.singleShot(3000, shot_sit)
sys.exit(app.exec())
