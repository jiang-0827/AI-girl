"""语音合成引擎 - 通义千问 Qwen-TTS 合成 + QMediaPlayer 播放"""
import os
import tempfile
import requests
from PySide6.QtCore import QUrl, QObject, Signal
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# Qwen-TTS 走 multimodal-generation 接口
TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

# 可用音色
VOICES = {
    "Cherry（芊芊·甜美女声）": "Cherry",
    "Serena（苏瑶·温柔女声）": "Serena",
    "Ethan（晨煦·阳光男声）": "Ethan",
    "Chelsie（千雪·二次元女声）": "Chelsie",
}


class TTSEngine(QObject):
    """合成并播放语音，播放结束发 finished 信号"""
    speakStarted = Signal()
    speakFinished = Signal()
    error = Signal(str)

    def __init__(self, api_key: str, voice: str = "Cherry", parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self.voice = voice
        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.setPlaybackRate(1.25)  # 语速 1.25 倍
        self._player.mediaStatusChanged.connect(self._on_status)

    def set_params(self, api_key=None, voice=None):
        if api_key is not None:
            self.api_key = api_key
        if voice is not None:
            self.voice = voice

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.speakFinished.emit()

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def stop(self):
        self._player.stop()

    def get_audio_url(self, text: str) -> str:
        """调用 Qwen-TTS，返回音频临时 URL"""
        if not self.api_key:
            raise ValueError("未配置 API Key，无法合成语音")
        payload = {
            "model": "qwen-tts",
            "input": {"text": text},
            "parameters": {"voice": self.voice},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(TTS_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"TTS 错误 {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        output = data.get("output", {})
        audio = output.get("audio", {})
        url = audio.get("url")
        if not url:
            raise RuntimeError(f"TTS 未返回音频: {str(data)[:200]}")
        return url

    def speak(self, text: str):
        """下载并播放合成语音"""
        text = self._clean(text)
        if not text:
            return
        try:
            url = self.get_audio_url(text)
        except Exception as e:
            self.error.emit(str(e))
            return
        self._player.setSource(QUrl(url))
        self._player.play()
        self.speakStarted.emit()

    def _clean(self, text: str) -> str:
        """只保留适合朗读的文本：中文、英文、数字、基本句读；
        去掉 emoji、颜文字、波浪号~、markdown 与装饰符号，避免被 TTS 逐字念出（如把 ~ 念成“Ω”）。"""
        if not text:
            return ""
        import re
        # 先删常见颜文字 / emoji 组合
        text = re.sub(r"[\(（\[＜<][^\)）\]＞>]{0,6}[\)）\]＞>]", "", text)  # (..) (^_^) 等括号脸
        text = re.sub(r"[~～\^\*\+·•☆★♥♡ω▽□■▲▼→←↑↓]+", " ", text)          # 波浪号/颜文字构件/箭头
        # 保留：CJK、ASCII 字母数字、常见中文句读与空白；其余（emoji 等）丢弃
        keep = set("，。？！、；：,.?!;:%")
        out = []
        for ch in text:
            o = ord(ch)
            if "\u4e00" <= ch <= "\u9fff":       # 中文
                out.append(ch)
            elif ("a" <= ch <= "z" or "A" <= ch <= "Z" or "0" <= ch <= "9") and o < 0x7f:
                out.append(ch)
            elif ch in keep:
                out.append(ch)
            elif ch in " \n\t":
                out.append(" ")
            # 其他字符（emoji、颜文字残留、装饰符号）一律丢弃
        text = "".join(out)
        text = re.sub(r"\s+", " ", text).strip()
        return text
