"""生成占位角色图片和托盘图标"""
from PIL import Image, ImageDraw
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, 'assets')
os.makedirs(ASSETS, exist_ok=True)


def make_character():
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 身体（圆形）
    body_color = (129, 199, 250, 255)     # 天蓝
    belly_color = (255, 255, 255, 255)    # 白肚皮
    outline = (60, 90, 130, 255)

    # 主体圆
    d.ellipse([70, 90, 442, 462], fill=body_color, outline=outline, width=6)
    # 肚皮
    d.ellipse([150, 220, 362, 430], fill=belly_color)

    # 耳朵
    d.polygon([(130, 130), (100, 30), (210, 110)], fill=body_color, outline=outline)
    d.polygon([(382, 130), (412, 30), (302, 110)], fill=body_color, outline=outline)

    # 眼睛
    d.ellipse([180, 200, 230, 260], fill=(40, 40, 40, 255))
    d.ellipse([282, 200, 332, 260], fill=(40, 40, 40, 255))
    # 高光
    d.ellipse([195, 215, 212, 232], fill=(255, 255, 255, 255))
    d.ellipse([297, 215, 314, 232], fill=(255, 255, 255, 255))

    # 腮红
    d.ellipse([140, 280, 180, 310], fill=(255, 170, 180, 200))
    d.ellipse([332, 280, 372, 310], fill=(255, 170, 180, 200))

    # 嘴巴
    d.arc([220, 270, 292, 330], start=10, end=170, fill=(60, 40, 40, 255), width=5)

    # 脚
    d.ellipse([170, 430, 240, 480], fill=body_color, outline=outline, width=4)
    d.ellipse([272, 430, 342, 480], fill=body_color, outline=outline, width=4)

    img.save(os.path.join(ASSETS, 'character.png'))
    print('character.png 已生成')


def make_tray_icon():
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([6, 6, 58, 58], fill=(129, 199, 250, 255), outline=(60, 90, 130, 255), width=3)
    d.ellipse([20, 24, 28, 32], fill=(40, 40, 40, 255))
    d.ellipse([36, 24, 44, 32], fill=(40, 40, 40, 255))
    d.arc([22, 34, 42, 48], start=10, end=170, fill=(60, 40, 40, 255), width=2)
    img.save(os.path.join(ASSETS, 'tray_icon.png'))
    print('tray_icon.png 已生成')


if __name__ == '__main__':
    make_character()
    make_tray_icon()
