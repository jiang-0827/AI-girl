"""语音合成引擎 - 多 Provider 支持

- qwen:   通义千问 Qwen-TTS（DashScope multimodal-generation 接口）
- openai: OpenAI 兼容 /audio/speech（可接 OpenAI、DeepSeek、MiniMax、硅基流动等）

统一流程：合成 → 下载为本地临时文件 → QMediaPlayer 播放本地文件
（避免流媒体临时 URL 断流/过期导致播放中断，且本地播放可稳定 1.25× 倍速）
"""
import os
import time
import tempfile
import requests
from PySide6.QtCore import QUrl, QObject, Signal
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# 通义千问 Qwen-TTS 走 multimodal-generation 接口
QWEN_TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

# 可用音色（通义）
QWEN_VOICES = {
    "Cherry（芊芊·甜美女声）": "Cherry",
    "Serena（苏瑶·温柔女声）": "Serena",
    "Ethan（晨煦·阳光男声）": "Ethan",
    "Chelsie（千雪·二次元女声）": "Chelsie",
}

# OpenAI 兼容常见音色
OPENAI_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

PROVIDER_NAMES = {
    "qwen": "通义千问 Qwen-TTS",
    "openai": "OpenAI 兼容 /audio/speech",
}


def synthesize_qwen(api_key: str, model: str, voice: str, text: str) -> bytes:
    """调用 Qwen-TTS，返回音频字节"""
    payload = {
        "model": model or "qwen-tts",
        "input": {"text": text},
        "parameters": {"voice": voice or "Cherry"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(QWEN_TTS_URL, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise RuntimeError(f"Qwen-TTS 错误 {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    audio = (data.get("output") or {}).get("audio") or {}
    url = audio.get("url")
    if not url:
        raise RuntimeError(f"Qwen-TTS 未返回音频: {str(data)[:200]}")
    r2 = requests.get(url, timeout=90)
    r2.raise_for_status()
    return r2.content


def synthesize_openai_compat(api_key: str, base_url: str, model: str, voice: str, text: str) -> bytes:
    """调用 OpenAI 兼容 /audio/speech，返回音频字节"""
    if not base_url:
        raise RuntimeError("未配置 OpenAI 兼容 TTS 地址（如 https://api.openai.com/v1）")
    url = base_url.rstrip("/") + "/audio/speech"
    payload = {
        "model": model or "tts-1",
        "input": text,
        "voice": voice or "alloy",
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise RuntimeError(f"TTS 错误 {resp.status_code}: {resp.text[:200]}")
    return resp.content


class TTSEngine(QObject):
    """合成并播放语音，播放结束发 finished 信号"""
    speakStarted = Signal()
    speakFinished = Signal()
    error = Signal(str)

    def __init__(self, api_key: str, voice: str = "Cherry", parent=None,
                 provider: str = "qwen", base_url: str = "", model: str = ""):
        super().__init__(parent)
        self.api_key = api_key
        self.voice = voice
        self.provider = provider or "qwen"
        self.base_url = base_url or ""
        self.model = model or ""
        self._tmp_path = None
        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.setPlaybackRate(1.25)  # 语速 1.25 倍
        self._player.mediaStatusChanged.connect(self._on_status)

    def set_params(self, api_key=None, voice=None, provider=None, base_url=None, model=None):
        if api_key is not None:
            self.api_key = api_key
        if voice is not None:
            self.voice = voice
        if provider is not None:
            self.provider = provider
        if base_url is not None:
            self.base_url = base_url
        if model is not None:
            self.model = model

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._cleanup_tmp()
            self.speakFinished.emit()

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def stop(self):
        self._player.stop()

    def _cleanup_tmp(self):
        if self._tmp_path and os.path.exists(self._tmp_path):
            try:
                os.remove(self._tmp_path)
            except OSError:
                pass
        self._tmp_path = None

    def _synthesize(self, text: str) -> bytes:
        if self.provider == "openai":
            return synthesize_openai_compat(self.api_key, self.base_url, self.model, self.voice, text)
        return synthesize_qwen(self.api_key, self.model, self.voice, text)

    def speak(self, text: str):
        """合成并播放语音（先下载到本地临时文件，播放更完整稳定）"""
        text = self._clean(text)
        if not text:
            return
        try:
            audio = self._synthesize(text)
            if not audio:
                raise RuntimeError("合成结果为空")
        except Exception as e:
            self.error.emit(str(e))
            return
        # 写入本地临时文件再播放（探测真实格式：Qwen 返回 WAV，OpenAI 兼容返回 MP3）
        self._cleanup_tmp()
        try:
            fd, path = tempfile.mkstemp(suffix=".bin")
            with os.fdopen(fd, "wb") as f:
                f.write(audio)
            with open(path, "rb") as f:
                head = f.read(4)
            ext = ".wav" if head.startswith(b"RIFF") else ".mp3"
            final = path[:-4] + ext
            os.replace(path, final)
            path = final
        except OSError as e:
            self.error.emit(f"临时文件写入失败: {e}")
            return
        self._tmp_path = path
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self.speakStarted.emit()

    def _clean(self, text: str) -> str:
        """只保留适合朗读的文本：中文、英文、数字、基本句读；
        去掉 emoji、颜文字、波浪号~、markdown 与装饰符号，避免被 TTS 逐字念出（如把 ~ 念成“Ω”）。"""
        if not text:
            return ""
        import re
        text = re.sub(r"[\(（\[＜<][^\)）\]＞>]{0,6}[\)）\]＞>]", "", text)  # (..) (^_^) 等括号脸
        text = re.sub(r"[~～\^\*\+·•☆★♥♡ω▽□■▲▼→←↑↓]+", " ", text)          # 波浪号/颜文字构件/箭头
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
        text = "".join(out)
        text = re.sub(r"\s+", " ", text).strip()
        return text
