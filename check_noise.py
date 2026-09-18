# -*- coding: utf-8 -*-
"""检查坐姿帧：角色包围盒外的深色噪点"""
from PIL import Image
import numpy as np
import glob

for p in sorted(glob.glob(r'E:\DesktopPetAI\assets\anim\sit-*.png')):
    a = np.asarray(Image.open(p))
    alpha = a[:, :, 3] > 60
    ys, xs = np.where(alpha)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    dark = (a[:, :, 0] < 100) & (a[:, :, 1] < 100) & (a[:, :, 2] < 100) & alpha
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    in_box = (xx >= x0 + 30) & (xx <= x1 - 30) & (yy >= y0 + 30) & (yy <= y1 - 30)
    outside_n = int((dark & ~in_box).sum())
    print(p.split('\\')[-1], 'bbox', (x0, y0, x1, y1), 'dark-outside-box:', outside_n)
