# -*- coding: utf-8 -*-
"""精确定位：抓取窗口当前帧，与 sit/idle 各帧像素比对"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from ui.pet_window import PetWindow
from PIL import Image
import numpy as np

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
w = PetWindow()
w.show()

refs = {}
for name in ['sit', 'idle']:
    for i in range(1, 5):
        p = rf'E:\DesktopPetAI\assets\anim\{name}-0{i}.png'
        im = Image.open(p).convert('RGBA').resize((64, 64), Image.LANCZOS)
        arr = np.asarray(im).astype(np.float32)
        refs[f'{name}-0{i}'] = (arr[:, :, :3], arr[:, :, 3] > 100)

def best_match(pm):
    img = pm.toImage()
    w2, h2 = img.width(), img.height()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h2, w2, 4)[:, :, :3].copy()
    arr = np.asarray(Image.fromarray(arr).resize((64, 64), Image.LANCZOS)).astype(np.float32)
    best, score = None, 1e18
    for k, (rgb, mask) in refs.items():
        diff = np.abs(arr - rgb).mean(axis=2)
        d = diff[mask].mean() if mask.sum() > 0 else 1e9
        if d < score:
            score, best = d, k
    return best, round(float(score), 2)

def check():
    st = w.animator.current_state()
    act = w.animator._active[0] if w.animator._active else None
    idx = w.animator._idx
    pm = w.label.pixmap()
    best, score = best_match(pm)
    print(f"state={st} active={act} idx={idx} best={best} score={score}")

def run():
    w.animator.play('sit')
    check()
    QTimer.singleShot(700, lambda: check())
    QTimer.singleShot(1400, lambda: check())
    QTimer.singleShot(2100, lambda: (check(), app.quit()))

QTimer.singleShot(3000, run)
sys.exit(app.exec())
