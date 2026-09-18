# -*- coding: utf-8 -*-
"""清理坐姿帧孤立噪点：删除面积小于阈值的深色连通域（保留黑裙/蝴蝶结等主体）"""
from PIL import Image, ImageFilter
import numpy as np
from collections import deque
import glob


def remove_small_clusters(dark: np.ndarray, min_size: int = 40) -> np.ndarray:
    """在 dark 掩码上标记连通域，删除面积 < min_size 的簇"""
    h, w = dark.shape
    visited = np.zeros_like(dark, dtype=bool)
    keep = dark.copy()
    for sy in range(h):
        for sx in range(w):
            if dark[sy, sx] and not visited[sy, sx]:
                # BFS
                q = deque([(sy, sx)])
                visited[sy, sx] = True
                cells = []
                while q:
                    cy, cx = q.popleft()
                    cells.append((cy, cx))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if dy == 0 and dx == 0:
                                continue
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < h and 0 <= nx < w and dark[ny, nx] and not visited[ny, nx]:
                                visited[ny, nx] = True
                                q.append((ny, nx))
                if len(cells) < min_size:
                    for cy, cx in cells:
                        keep[cy, cx] = False
    return keep


for path in sorted(glob.glob(r'E:\DesktopPetAI\assets\anim\sit-*.png')):
    im = Image.open(path)
    a = np.asarray(im).astype(np.int16)
    alpha = a[:, :, 3] > 60
    dark = (a[:, :, 0] < 100) & (a[:, :, 1] < 100) & (a[:, :, 2] < 100) & alpha
    cleaned = remove_small_clusters(dark, min_size=40)
    removed = int((dark & ~cleaned).sum())
    # 边缘 18px 内残影一并透明
    h, w = alpha.shape
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy))
    edge_clean = dist < 18
    alpha_new = a[:, :, 3].copy()
    alpha_new[cleaned == False] = 0          # noqa: 删噪点
    alpha_new[edge_clean & (alpha_new > 0) & (a[:, :, 0] < 110)] = 0  # 边缘暗色残影
    out = Image.fromarray(np.dstack([a[:, :, :3].astype(np.uint8), alpha_new.astype(np.uint8)]), 'RGBA')
    am = out.split()[3]
    am = am.filter(ImageFilter.MaxFilter(3))
    am = am.filter(ImageFilter.GaussianBlur(0.6))
    out.putalpha(am)
    out.save(path)
    print(path.split('\\')[-1], 'removed small clusters:', removed, 'pixels')
