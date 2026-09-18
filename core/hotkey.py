"""全局热键监听 - 使用 pynput"""
from PySide6.QtCore import QObject, Signal

try:
    from pynput import keyboard
    _PYNPUT = True
except ImportError:
    _PYNPUT = False


class HotkeyManager(QObject):
    """注册全局热键，触发时发出 activated 信号"""
    activated = Signal()

    def __init__(self, hotkey_str: str = "<ctrl>+<shift>+<space>", parent=None):
        super().__init__(parent)
        self.hotkey_str = hotkey_str
        self._listener = None

    def start(self):
        if not _PYNPUT:
            print("pynput 未安装，全局热键不可用")
            return
        try:
            self._listener = keyboard.GlobalHotKeys({
                self.hotkey_str: self._on_hit
            })
            self._listener.daemon = True
            self._listener.start()
        except Exception as e:
            print(f"热键注册失败: {e}")

    def _on_hit(self):
        # pynput 回调在非 GUI 线程，通过 signal 转投主线程
        self.activated.emit()

    def stop(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
