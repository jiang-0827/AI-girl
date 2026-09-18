# -*- coding: utf-8 -*-
"""TTS 播放诊断：真实合成并播放一段长文本，记录播放器状态与时长"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from config import load_config
from core.tts_engine import TTSEngine

app = QApplication(sys.argv)
cfg = load_config()
key = cfg.get("api_key", "")
tts = TTSEngine(key, cfg.get("tts_voice", "Cherry"))

log = []

def on_status(s):
    log.append(("status", int(s.value if hasattr(s, "value") else s), getattr(s, "name", "")))
    if s == QMediaPlayer.MediaStatus.EndOfMedia:
        dur = tts._player.duration()
        pos = tts._player.position()
        print(f"[EndOfMedia] duration={dur}ms position={pos}ms rate={tts._player.playbackRate()}")
        finish()
    elif s in (QMediaPlayer.MediaStatus.InvalidMedia, QMediaPlayer.MediaStatus.StalledMedia):
        print(f"[异常] status={s}  error={tts._player.error()}: {tts._player.errorString()}")

def on_pos(p):
    pass  # 采样由 timer 做

tts._player.mediaStatusChanged.connect(on_status)
tts._player.positionChanged.connect(on_pos)
tts.error.connect(lambda m: print("[TTS ERROR]", m))

started = {"t": None}
def on_started():
    started["t"] = time_ms()
    print("[speakStarted]")

tts.speakStarted.connect(on_started)

def time_ms():
    import time
    return int(time.time() * 1000)

text = ("你好呀，我是你的桌面小助手蓝蓝。今天天气不错，记得多喝水哦。"
        "我可以在你工作的时候陪你聊天，帮你打开应用、调整音量，还可以提醒你重要的事情。"
        "如果你累了，就摸摸我的头吧，我会很开心。")

print("=== 开始播放，文本长度:", len(text), "===")
tts.speak(text)
t0 = time_ms()

def poll():
    el = time_ms() - t0
    pos = tts._player.position()
    dur = tts._player.duration()
    state = tts._player.playbackState()
    print(f"[poll {el}ms] state={state} pos={pos} dur={dur} isPlaying={tts.is_playing()}")
    if el > 45000:
        print("=== 45s 超时，判定未播完 ===")
        finish()
        return
    QTimer.singleShot(1000, poll)

def finish():
    print("=== 播放结束检查 ===")
    pos = tts._player.position()
    dur = tts._player.duration()
    print(f"final pos={pos}ms dur={dur}ms rate={tts._player.playbackRate()}")
    print("媒体状态序列:", [(s[1], s[2]) for s in log])
    app.quit()

tts.speakStarted.connect(lambda: QTimer.singleShot(200, poll))
QTimer.singleShot(60000, finish)
sys.exit(app.exec())
