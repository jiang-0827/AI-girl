"""语音识别引擎 - 通义千问 Qwen-Audio-ASR，支持 base64 data URL 上传"""
import base64
import requests
from PyQt5.QtCore import QThread, pyqtSignal

ASR_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


class ASREngine:
    def __init__(self, api_key: str, model: str = "qwen-audio-asr"):
        self.api_key = api_key
        self.model = model

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    def recognize(self, wav_bytes: bytes) -> str:
        """把 WAV 字节识别为文字"""
        if not self.api_key:
            raise ValueError("未配置 API Key，无法识别语音")
        if not wav_bytes:
            return ""
        b64 = base64.b64encode(wav_bytes).decode()
        data_url = f"data:audio/wav;base64,{b64}"
        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {"role": "system", "content": [{"text": "你是语音转写助手，只输出识别出的文本内容。"}]},
                    {"role": "user", "content": [
                        {"audio": data_url},
                        {"text": "转写这段语音为文字"},
                    ]},
                ]
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(ASR_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"ASR 错误 {resp.status_code}: {resp.text[:200]}")
        return self._extract_text(resp.json())

    def _extract_text(self, data: dict) -> str:
        out = data.get("output", {})
        # 路径1：output.choices[0].message.content
        choices = out.get("choices")
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            if isinstance(content, list):
                return "".join(c.get("text", "") for c in content if isinstance(c, dict))
            return str(content)
        # 路径2：output.text
        if "text" in out:
            return str(out["text"])
        return ""


class ASRWorker(QThread):
    """后台线程执行语音识别"""
    recognized = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, engine: ASREngine, wav_bytes: bytes, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.wav_bytes = wav_bytes

    def run(self):
        try:
            text = self.engine.recognize(self.wav_bytes)
            self.recognized.emit(text.strip())
        except Exception as e:
            self.error.emit(str(e))
