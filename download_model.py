"""从国内镜像下载 rembg 的 u2net.onnx 模型，放到 rembg 会查找的目录"""
import os
import sys
import requests

MIRRORS = [
    "https://gh-proxy.com/https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
    "https://ghfast.top/https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
    "https://mirror.ghproxy.com/https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
    "https://gitclone.com/github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
]

HOME = os.path.expanduser("~")
TARGETS = [
    os.path.join(HOME, ".u2net", "u2net.onnx"),
    os.path.join(HOME, ".rembg", "models", "u2net", "u2net.onnx"),
]


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
        if total and done < total * 0.9:
            raise RuntimeError("下载不完整")
    os.replace(tmp, dest)
    return os.path.getsize(dest)


def main():
    for url in MIRRORS:
        print("尝试镜像:", url)
        try:
            size = download(url, TARGETS[0])
            print(f"下载成功 {size/1e6:.1f} MB -> {TARGETS[0]}")
            # 复制到第二个位置
            for t in TARGETS[1:]:
                os.makedirs(os.path.dirname(t), exist_ok=True)
                try:
                    import shutil
                    shutil.copy2(TARGETS[0], t)
                    print("已复制到", t)
                except Exception as e:
                    print("复制失败", t, e)
            return
        except Exception as e:
            print("  失败:", repr(e)[:150])
    print("所有镜像均失败")
    sys.exit(1)


if __name__ == "__main__":
    main()
