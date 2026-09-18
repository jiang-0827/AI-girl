# -*- coding: utf-8 -*-
"""绿幕抠图：删除纯绿背景、去绿边、羽化、缩放到 512x512"""
from PIL import Image, ImageFilter
import numpy as np
import glob
import os


def key_out(path: str):
    im = Image.open(path).convert('RGB')
    a = np.asarray(im).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    # 绿幕判据：绿色通道显著高于红蓝
    bg = (g > r + 45) & (g > b + 45) & (g > 110)
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    # despill：边缘残绿减绿
    edge = (~bg) & (g > r + 18) & (g > b + 10)
    a[edge, 1] = np.minimum(a[edge, 1], np.maximum(a[edge, 0], a[edge, 2]) + 6)
    out_im = Image.fromarray(np.dstack([a.astype(np.uint8), alpha]), 'RGBA')
    # 形态学清理 + 边缘羽化
    am = out_im.split()[3]
    am = am.filter(ImageFilter.MaxFilter(3))
    am = am.filter(ImageFilter.GaussianBlur(1.2))
    out_im.putalpha(am)
    out_im = out_im.resize((512, 512), Image.LANCZOS)
    out_im.save(path)
    print('processed:', os.path.basename(path))


for p in sorted(glob.glob(r'E:\DesktopPetAI\assets\anim\sit-*.png')):
    key_out(p)
