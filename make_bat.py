"""生成双击启动用的 .bat 文件到 E:\\DesktopPetAI"""
import os

dst = r"E:\DesktopPetAI"

# 静默启动（无黑窗口，用 pythonw）
b1 = '@echo off\r\ncd /d "%~dp0"\r\nstart "" pythonw main.py\r\n'
# 带控制台窗口启动（方便看报错）
b2 = '@echo off\r\ncd /d "%~dp0"\r\npython main.py\r\npause\r\n'

with open(os.path.join(dst, "启动桌宠.bat"), "w", encoding="gbk") as f:
    f.write(b1)
with open(os.path.join(dst, "启动(带窗口).bat"), "w", encoding="gbk") as f:
    f.write(b2)
print("已生成:", os.listdir(dst)[:0] or "启动桌宠.bat / 启动(带窗口).bat")
