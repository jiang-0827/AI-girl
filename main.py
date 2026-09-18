"""桌面 AI 悬浮伴侣 - 程序入口"""
import sys
import os

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

from config import load_config, save_config
from ui.pet_window import PetWindow


def maybe_first_run_guidance(app):
    cfg = load_config()
    if cfg.get("first_run", True) or not cfg.get("api_key"):
        msg = (
            "欢迎使用 桌面 AI 悬浮伴侣！\n\n"
            "首次使用请配置「通义千问 API Key」：\n"
            "1. 访问 https://dashscope.console.aliyun.com/ 申请 API Key\n"
            "2. 在设置窗口的「AI」标签页粘贴 Key\n\n"
            "小技巧：\n"
            "• 拖动角色可移动位置\n"
            "• 单击角色 / 按 Ctrl+Shift+Space 打开聊天\n"
            "• 右键角色或托盘图标打开菜单\n\n"
            "现在打开设置进行配置吗？"
        )
        box = QMessageBox()
        box.setWindowTitle("首次使用")
        box.setText(msg)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("现在配置")
        box.button(QMessageBox.No).setText("稍后再说")
        if box.exec_() == QMessageBox.Yes:
            return True  # 需要打开设置
        cfg["first_run"] = False
        save_config(cfg)
    return False


def main():
    # 高分屏适配
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭聊天窗不退出程序

    pet = PetWindow()
    pet.show()

    if maybe_first_run_guidance(app):
        pet.open_settings()
        cfg = load_config()
        cfg["first_run"] = False
        save_config(cfg)

    # 启动欢迎气泡
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(600, lambda: pet._show_bubble("嗨！我是你的桌面小助手 🐾"))

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
