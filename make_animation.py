"""基于透明头像生成：眨眼帧 character_blink.png、托盘图标 tray_icon.png、应用图标 app.ico"""
import os
import numpy as np
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(BASE, "assets")
CHAR = os.path.join(A, "character.png")

# 眼睛框（相对宽高比例 x0,y0,x1,y1），换图后可微调这几个值
EYES = [
    (0.335, 0.470, 0.485, 0.595),   # 左眼
    (0.515, 0.470, 0.665, 0.595),   # 右眼
]


def make_blink(img):
    W, H = img.size
    arr = np.array(img).copy()
    out = arr.copy()
    for (rx0, ry0, rx1, ry1) in EYES:
        x0, y0, x1, y1 = int(rx0 * W), int(ry0 * H), int(rx1 * W), int(ry1 * H)
        sy = min(H - 1, y1 + 12)                    # 眼睛下方脸颊
        colskin = arr[sy, x0:x1, :].astype(int).copy()   # (w,4) 逐列皮肤
        lum = colskin[:, :3].sum(1)
        med = np.median(colskin[:, :3], axis=0).astype(int)
        thr = np.percentile(lum, 40) if len(lum) else 0
        for i in range(len(colskin)):               # 暗列(眼线/阴影)换成中位肤色
            if lum[i] < thr:
                colskin[i, :3] = med
        out[y0:y1, x0:x1] = colskin[None, :, :].astype(np.uint8)
    blink = Image.fromarray(out)
    d = ImageDraw.Draw(blink)
    lash = (70, 58, 82, 255)
    for (rx0, ry0, rx1, ry1) in EYES:
        x0, y0, x1, y1 = int(rx0 * W), int(ry0 * H), int(rx1 * W), int(ry1 * H)
        ly = y0 + int((y1 - y0) * 0.45)             # 上眼睑落下位置
        d.arc([x0 + 2, ly - 8, x1 - 2, ly + 8], start=15, end=165, fill=lash, width=3)
    return blink


def to_square(img, size):
    """居中放到透明方画布"""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    im = img.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    ox = (size - im.width) // 2
    oy = (size - im.height) // 2
    canvas.paste(im, (ox, oy), im)
    return canvas


def main():
    img = Image.open(CHAR).convert("RGBA")

    blink = make_blink(img)
    blink.save(os.path.join(A, "character_blink.png"))
    print("character_blink.png 已生成", blink.size)

    # 托盘图标（256 方画布）
    sq = to_square(img, 256)
    sq.save(os.path.join(A, "tray_icon.png"))
    print("tray_icon.png 已生成")

    # 应用 ico 多尺寸
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    sq.save(os.path.join(A, "app.ico"), format="ICO", sizes=ico_sizes)
    print("app.ico 已生成")


if __name__ == "__main__":
    main()
