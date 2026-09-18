"""录音模块 - 用 sounddevice 采集 16kHz 单声道 WAV"""
import io
import wave
import numpy as np

try:
    import sounddevice as sd
    _SD = True
except Exception:
    _SD = False

SAMPLE_RATE = 16000
CHANNELS = 1
MAX_SECONDS = 15


class AudioRecorder:
    def __init__(self):
        self.recording = False
        self._frames = []

    @staticmethod
    def available() -> bool:
        return _SD

    def start(self):
        if not _SD:
            raise RuntimeError("sounddevice 未安装，无法录音")
        self._frames = []
        self.recording = True

        def callback(indata, frames, time_info, status):
            if self.recording:
                self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
            callback=callback, blocksize=1024,
        )
        self._stream.start()

    def stop_to_wav_bytes(self) -> bytes:
        """停止录音，返回 WAV 格式字节流"""
        self.recording = False
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        if not self._frames:
            return b""
        audio = np.concatenate(self._frames, axis=0).flatten()
        # 归一到 int16
        peak = np.max(np.abs(audio)) if audio.size else 0
        if peak > 0:
            audio = audio / max(peak, 1e-6) * 32767 * 0.9
        audio = np.clip(audio, -32768, 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()

    def duration(self) -> float:
        n = sum(f.shape[0] for f in self._frames) if self._frames else 0
        return n / SAMPLE_RATE
