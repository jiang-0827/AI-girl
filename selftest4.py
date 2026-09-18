# -*- coding: utf-8 -*-
"""气泡避让测试：AI 气泡与用户气泡同时显示时不得重叠"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QPoint
from ui.chat_bubble import ChatBubble

app = QApplication(sys.argv)

base = QPoint(320, 300)
size = 176

ai = ChatBubble(role="ai", align="left")
user = ChatBubble(role="user", align="right")

def tail_ai():
    return (base.x() + int(size * 0.62), base.y() + 4)

def tail_user():
    return (base.x() + int(size * 0.38), base.y() + 4)

# 1) 用户气泡先显示
ux, uy = tail_user()
user.show_text("我想要一个比较长的用户消息气泡内容哦", ux, uy)

# 2) AI 气泡随后显示，应避让用户气泡（重叠则上移）
ai.set_avoid(user.geometry())
ax, ay = tail_ai()
ai.show_text("好的呀，这是 AI 的回复内容，也写得比较长一些", ax, ay)

r1, r2 = ai.geometry(), user.geometry()
print(f"ai   : x={r1.x()} y={r1.y()} w={r1.width()} h={r1.height()}")
print(f"user : x={r2.x()} y={r2.y()} w={r2.width()} h={r2.height()}")
print("intersects:", r1.intersects(r2))
assert not r1.intersects(r2), "FAIL: AI 与用户气泡仍然重叠！"

# 3) 反向：AI 先显示，用户气泡后显示避让
ai2 = ChatBubble(role="ai", align="left")
user2 = ChatBubble(role="user", align="right")
ax, ay = tail_ai()
ai2.show_text("AI 先说话的内容也很长很长", ax, ay)
user2.set_avoid(ai2.geometry())
ux, uy = tail_user()
user2.show_text("然后用户再说话的内容也很长", ux, uy)
r3, r4 = ai2.geometry(), user2.geometry()
print("reverse intersects:", r3.intersects(r4))
assert not r3.intersects(r4), "FAIL: 反向场景气泡重叠！"

# 4) 角色移动后（_reposition 场景）依然不重叠
base = QPoint(420, 320)
ax, ay = tail_ai()
ai.set_avoid(user.geometry())
ai.update_text("角色移动后的 AI 内容", ax, ay)
ux, uy = tail_user()
user.set_avoid(ai.geometry())
user.update_text("角色移动后的用户内容", ux, uy)
r5, r6 = ai.geometry(), user.geometry()
print("after move intersects:", r5.intersects(r6))
assert not r5.intersects(r6), "FAIL: 角色移动后气泡重叠！"

print("AVOID TEST OK")
QTimer.singleShot(100, app.quit)
sys.exit(app.exec())
