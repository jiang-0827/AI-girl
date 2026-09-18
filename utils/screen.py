"""多显示器虚拟桌面坐标工具

统一使用「虚拟桌面」坐标（所有显示器几何的并集，含负坐标与跨屏偏移），
避免用单主屏 availableGeometry 做 clamp 导致窗口无法拖到副屏。
"""
from PyQt5.QtCore import QRect
from PyQt5.QtWidgets import QApplication


def virtual_desktop_rect() -> QRect:
    """返回所有显示器组成的虚拟桌面矩形（可能包含负坐标）。"""
    app = QApplication.instance()
    rect = QRect()
    if app is not None:
        try:
            for s in app.screens():
                rect = rect.united(s.geometry())
        except Exception:
            rect = QRect()
    if rect.isNull():
        # 兜底：用 desktop().virtualGeometry()
        try:
            rect = QApplication.desktop().virtualGeometry()
        except Exception:
            rect = QRect(0, 0, 1920, 1080)
    if rect.isNull():
        rect = QRect(0, 0, 1920, 1080)
    return rect


def clamp_to_virtual(x: int, y: int, w: int, h: int):
    """把窗口左上角限制在虚拟桌面内（允许负坐标），尽量保证窗口完整可见。

    与主屏裁剪不同：这里以整个多屏虚拟桌面为边界，副屏（含左侧/上方的负坐标）
    也能正常显示。
    """
    r = virtual_desktop_rect()
    min_x, min_y = r.left(), r.top()
    # 右/下边界：保证整窗可见
    max_x = r.right() - w + 1
    max_y = r.bottom() - h + 1
    # 若窗口比虚拟桌面还大，则贴左上
    if max_x < min_x:
        max_x = min_x
    if max_y < min_y:
        max_y = min_y
    cx = max(min_x, min(int(x), max_x))
    cy = max(min_y, min(int(y), max_y))
    return cx, cy
