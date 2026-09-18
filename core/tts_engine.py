"""语音合成引擎 - 通义千问 Qwen-TTS 合成 + QMediaPlayer 播放"""
import os
import tempfile
import requests
from PyQt5.QtCore import QUrl, QObject, pyqtSignal
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

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
    speakStarted = pyqtSignal()
    speakFinished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, api_key: str, voice: str = "Cherry", parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self.voice = voice
        self._player = QMediaPlayer(self)
        self._player.mediaStatusChanged.connect(self._on_status)

    def set_params(self, api_key=None, voice=None):
        if api_key is not None:
            self.api_key = api_key
        if voice is not None:
            self.voice = voice

    def _on_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.speakFinished.emit()

    def is_playing(self) -> bool:
        return self._player.state() == QMediaPlayer.PlayingState

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
        self._player.setMedia(QMediaContent(QUrl(url)))
        self._player.play()
        self.speakStarted.emit()

    def _clean(self, text: str) -> str:
        # 去掉 emoji 和 markdown 符号，避免念出来
        import re
        text = re.sub(r"[*_`#>\[\]]", "", text)
        # 去除非 BMP 字符（emoji）
        text = "".join(ch for ch in text if ord(ch) < 0x10000)
        return text.strip()
