"""把用户提供的形象图处理成桌宠透明 PNG
优先用 rembg 抠除背景；若不可用则做圆角保底处理。
"""
import os
import sys
from PIL import Image, ImageDraw

SRC_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "avatar_src.webp"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "avatar_src.png"),
]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "character.png")


def find_src():
    for p in SRC_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def try_rembg(img):
    try:
        from rembg import remove, new_session
    except Exception:
        return None, "rembg 未安装"
    try:
        session = new_session("u2net")
        out = remove(img, session=session)
        return out, "rembg"
    except Exception as e:
        return None, f"rembg 失败: {e}"


def rounded_fallback(img, radius_ratio=0.18):
    """圆角遮罩保底"""
    w, h = img.size
    r = int(min(w, h) * radius_ratio)
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def main():
    src = find_src()
    if not src:
        print("找不到源图片")
        return
    print("源图:", src)
    img = Image.open(src).convert("RGBA")

    result, mode = try_rembg(img)
    if result is None:
        print("使用圆角保底:", mode)
        result = rounded_fallback(img)
    else:
        print("使用 AI 抠图 (rembg)")

    # 裁剪到内容边界
    bbox = result.getbbox()
    if bbox:
        result = result.crop(bbox)

    # 缩放到最大边 512
    max_side = 512
    w, h = result.size
    scale = max_side / max(w, h)
    if scale < 1:
        result = result.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    result.save(OUT)
    print("已保存:", OUT, result.size, "mode=", "transparent" if mode == "rembg" else "rounded")


if __name__ == "__main__":
    main()
