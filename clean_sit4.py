# -*- coding: utf-8 -*-
"""清理 sit-04 边缘噪点：图像边缘 24px 内的杂点置为透明"""
from PIL import Image, ImageFilter
import numpy as np

path = r'E:\DesktopPetAI\assets\anim\sit-04.png'
im = Image.open(path)
a = np.asarray(im).astype(np.int16)
h, w = a.shape[:2]
yy, xx = np.mgrid[0:h, 0:w]
dist = np.minimum(np.minimum(xx, w-1-xx), np.minimum(yy, h-1-yy))
edge = dist < 24
# 边缘区域：非透明且接近背景/深色杂点 → 置透明；浅色边缘像素也清理（绿幕残余）
alpha = a[:, :, 3]
dark = (a[:,:,0] < 90) & (a[:,:,1] < 90) & (a[:,:,2] < 90)
clean = edge & (alpha > 30) & (dark | ((a[:,:,2].astype(int) - a[:,:,0].astype(int)) < 8) & (a[:,:,0] < 150))
alpha[clean] = 0
out = Image.fromarray(a.astype(np.uint8), 'RGBA')
# 再羽化
am = out.split()[3]
am = am.filter(ImageFilter.GaussianBlur(0.8))
out.putalpha(am)
out.save(path)
print('cleaned edge pixels:', int(clean.sum()))
