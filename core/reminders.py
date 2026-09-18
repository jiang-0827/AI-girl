"""提醒调度器 - 管理定时提醒，到期回调；支持持久化到 reminders.json"""
import os
import json
import time
from PySide6.QtCore import QObject, QTimer

from utils.resource_path import app_dir

REMINDER_FILE = os.path.join(app_dir(), "reminders.json")


class ReminderScheduler(QObject):
    """每秒检查到期提醒，通过 on_fire 回调通知外部"""

    def __init__(self, on_fire, parent=None):
        super().__init__(parent)
        self._on_fire = on_fire          # callable(text, rid)
        self._items = {}                 # rid -> {"due": ts, "text": str}
        self._next_id = 1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._load()

    def add(self, seconds, text):
        rid = self._next_id
        self._next_id += 1
        self._items[rid] = {"due": time.time() + seconds, "text": text}
        self._save()
        return rid

    def cancel(self, rid):
        if rid in self._items:
            self._items.pop(rid)
            self._save()
            return f"已取消提醒 #{rid}"
        return f"没有找到提醒 #{rid}"

    def list_readable(self):
        now = time.time()
        out = []
        for rid, it in self._items.items():
            remain = max(0, int(it["due"] - now))
            out.append(f"#{rid} {it['text']}（约 {self._fmt(remain)}后）")
        return out

    def _fmt(self, sec):
        if sec >= 3600:
            return f"{sec//3600}小时{(sec%3600)//60}分"
        if sec >= 60:
            return f"{sec//60}分{sec%60}秒"
        return f"{sec}秒"

    def _tick(self):
        now = time.time()
        due = [rid for rid, it in self._items.items() if it["due"] <= now]
        for rid in due:
            it = self._items.pop(rid)
            self._save()
            try:
                self._on_fire(it["text"], rid)
            except Exception:
                pass

    # ---------- 持久化 ----------
    def _save(self):
        try:
            data = {"next_id": self._next_id,
                    "items": {str(k): v for k, v in self._items.items()}}
            with open(REMINDER_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self):
        try:
            if not os.path.exists(REMINDER_FILE):
                return
            with open(REMINDER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._next_id = data.get("next_id", 1)
            self._items = {int(k): v for k, v in data.get("items", {}).items()}
        except Exception:
            self._items = {}
