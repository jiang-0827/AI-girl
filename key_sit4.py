# -*- coding: utf-8 -*-
"""单独修复 sit-04：宽松阈值处理渐变绿幕"""
from PIL import Image, ImageFilter
import numpy as np

path = r'E:\DesktopPetAI\assets\anim\sit-04.png'
im = Image.open(path).convert('RGB')
a = np.asarray(im).astype(np.int16)
r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
# 宽松判据：绿通道明显高于红，且不低于蓝太多（覆盖青绿渐变）
bg = (g > r + 25) & (g > b - 15) & (g > 95)
alpha = np.where(bg, 0, 255).astype(np.uint8)
# despill
edge = (~bg) & (g > r + 14) & (g > b - 8)
a[edge, 1] = np.minimum(a[edge, 1], np.maximum(a[edge, 0], a[edge, 2]) + 6)
out_im = Image.fromarray(np.dstack([a.astype(np.uint8), alpha]), 'RGBA')
am = out_im.split()[3]
am = am.filter(ImageFilter.MaxFilter(3))
am = am.filter(ImageFilter.GaussianBlur(1.2))
out_im.putalpha(am)
out_im = out_im.resize((512, 512), Image.LANCZOS)
out_im.save(path)
print('sit-04 fixed, bg removed:', int((bg).sum()), 'pixels')
