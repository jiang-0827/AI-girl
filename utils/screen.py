"""多显示器虚拟桌面坐标工具

统一使用「虚拟桌面」坐标（所有显示器几何的并集，含负坐标与跨屏偏移），
避免用单主屏 availableGeometry 做 clamp 导致窗口无法拖到副屏。
"""
from PySide6.QtCore import QRect, QPoint
from PySide6.QtWidgets import QApplication


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


def screen_at(x: int, y: int):
    """返回包含全局坐标 (x,y) 的那个屏幕（QScreen）；找不到返回主屏。"""
    app = QApplication.instance()
    if app is None:
        return None
    pt = QPoint(int(x), int(y))
    try:
        for s in app.screens():
            if s.geometry().contains(pt):
                return s
    except Exception:
        pass
    return app.primaryScreen()


def screen_scale(x: int, y: int) -> float:
    """计算坐标所在屏幕相对主屏的缩放因子（基于分辨率/DPI 比例）。

    用于让输入条/气泡在切到不同分辨率的副屏时自动调整大小。
    限制在 [0.6, 1.6] 区间，避免极端值。
    """
    app = QApplication.instance()
    if app is None:
        return 1.0
    cur = screen_at(x, y)
    primary = app.primaryScreen()
    if cur is None or primary is None:
        return 1.0
    try:
        # 优先用 DPI 比例（反映 Windows 显示缩放），否则用分辨率比例
        dpi_cur = cur.logicalDotsPerInch()
        dpi_pri = primary.logicalDotsPerInch()
        if dpi_pri > 0:
            f = dpi_cur / dpi_pri
        else:
            f = 1.0
        # 若 DPI 几乎相同（HighDPI 被归一化），用可用宽度比例兼容不同分辨率屏
        if abs(f - 1.0) < 0.01:
            w_cur = cur.availableGeometry().width()
            w_pri = primary.availableGeometry().width()
            if w_pri > 0:
                f = w_cur / w_pri
    except Exception:
        f = 1.0
    return max(0.6, min(1.6, f))


def clamp_to_screen(x: int, y: int, w: int, h: int, px: int, py: int):
    """以坐标 (px,py) 所在屏幕为边界 clamp（允许负坐标），保证整窗在该屏内可见。"""
    s = screen_at(px, py)
    if s is None:
        return clamp_to_virtual(x, y, w, h)
    g = s.availableGeometry()
    min_x, min_y = g.left(), g.top()
    max_x = g.right() - w + 1
    max_y = g.bottom() - h + 1
    if max_x < min_x:
        max_x = min_x
    if max_y < min_y:
        max_y = min_y
    return max(min_x, min(int(x), max_x)), max(min_y, min(int(y), max_y))
