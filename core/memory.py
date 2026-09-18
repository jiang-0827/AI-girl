"""长期记忆 - 本地 SQLite 存储 + 通义 embedding 向量检索 + LLM 自动抽取
全部本地保存，跨会话持久。embedding/抽取失败时优雅降级为"最近记忆"。
"""
import os
import json
import time
import threading
import sqlite3

import numpy as np
import requests

from utils.resource_path import app_dir

MEMORY_DB = os.path.join(app_dir(), "memory.db")
EMBED_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

EXTRACT_PROMPT = (
    "你在维护「用户长期记忆」。请从下面这轮对话中，抽取关于用户本人的、值得长期记住的简短事实"
    "（例如姓名/称呼、喜好与厌恶、习惯、重要日期或计划）。"
    "只输出一个 JSON 数组，每项是一句不超过 30 字的中文陈述；若没有值得记住的信息则输出 []。"
    "不要臆造，不要输出除 JSON 以外的任何内容。\n"
)


class MemoryStore:
    def __init__(self, api_key="", emb_model="text-embedding-v3",
                 chat_model="qwen-turbo", topk=4, enabled=True):
        self.api_key = api_key
        self.emb_model = emb_model
        self.chat_model = chat_model
        self.topk = topk
        self.enabled = enabled
        self._lock = threading.Lock()
        self._init_db()

    # ---------- DB ----------
    def _init_db(self):
        with self._lock:
            con = sqlite3.connect(MEMORY_DB)
            con.execute("""CREATE TABLE IF NOT EXISTS memories(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                kind TEXT DEFAULT 'fact',
                embedding BLOB,
                created REAL
            )""")
            con.commit()
            con.close()

    def set_params(self, api_key=None, enabled=None, topk=None):
        if api_key is not None:
            self.api_key = api_key
        if enabled is not None:
            self.enabled = enabled
        if topk is not None:
            self.topk = topk

    # ---------- embedding ----------
    def _embed(self, texts):
        if not self.api_key or not texts:
            return None
        try:
            resp = requests.post(
                EMBED_URL,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.emb_model, "input": texts},
                timeout=30,
            )
            if resp.status_code != 200:
                return None
            data = sorted(resp.json()["data"], key=lambda d: d.get("index", 0))
            return [np.asarray(d["embedding"], dtype="float32") for d in data]
        except Exception:
            return None

    # ---------- 写入 ----------
    def add(self, text, kind="fact"):
        text = (text or "").strip()
        if not text:
            return
        vec = self._embed([text])
        blob = vec[0].tobytes() if vec else None
        with self._lock:
            con = sqlite3.connect(MEMORY_DB)
            # 去重：完全相同文本不重复存
            cur = con.execute("SELECT id FROM memories WHERE text=?", (text,))
            if cur.fetchone() is None:
                con.execute("INSERT INTO memories(text,kind,embedding,created) VALUES(?,?,?,?)",
                            (text, kind, blob, time.time()))
            con.commit()
            con.close()

    # ---------- 检索 ----------
    def recall(self, query, k=None):
        """返回与 query 最相关的若干条记忆文本。"""
        if not self.enabled:
            return []
        k = k or self.topk
        with self._lock:
            con = sqlite3.connect(MEMORY_DB)
            rows = con.execute(
                "SELECT text, embedding, created FROM memories ORDER BY created DESC LIMIT 500"
            ).fetchall()
            con.close()
        if not rows:
            return []
        qv = self._embed([query]) if query else None
        if qv is not None:
            qvec = qv[0]
            qnorm = np.linalg.norm(qvec) + 1e-9
            scored = []
            for text, blob, _created in rows:
                if blob is None:
                    continue
                mv = np.frombuffer(blob, dtype="float32")
                if mv.shape != qvec.shape:
                    continue
                sim = float(np.dot(qvec, mv) / (qnorm * (np.linalg.norm(mv) + 1e-9)))
                scored.append((sim, text))
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                return [t for s, t in scored[:k] if s > 0.30]
        # 降级：无 embedding 时返回最近 k 条
        return [text for text, _b, _c in rows[:k]]

    def as_system_block(self, query):
        """拼成注入 system prompt 的一段文本；无记忆返回空串。"""
        items = self.recall(query)
        if not items:
            return ""
        lines = "\n".join(f"- {t}" for t in items)
        return "\n\n【关于用户的长期记忆（请自然地遵循，不要生硬复述）】\n" + lines

    # ---------- 管理 ----------
    def all_memories(self):
        with self._lock:
            con = sqlite3.connect(MEMORY_DB)
            rows = con.execute(
                "SELECT id, text, datetime(created,'unixepoch','localtime') FROM memories ORDER BY created DESC LIMIT 200"
            ).fetchall()
            con.close()
        return rows

    def clear(self):
        with self._lock:
            con = sqlite3.connect(MEMORY_DB)
            con.execute("DELETE FROM memories")
            con.commit()
            con.close()

    def delete(self, mid):
        with self._lock:
            con = sqlite3.connect(MEMORY_DB)
            con.execute("DELETE FROM memories WHERE id=?", (int(mid),))
            con.commit()
            con.close()

    # ---------- 自动抽取（后台线程调用） ----------
    def extract_and_remember(self, user_text, reply_text):
        if not self.enabled or not self.api_key:
            return
        prompt = (EXTRACT_PROMPT +
                  f"用户说：{user_text}\n助手答：{reply_text}")
        try:
            resp = requests.post(
                CHAT_URL,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.chat_model,
                      "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.2},
                timeout=30,
            )
            if resp.status_code != 200:
                return
            content = resp.json()["choices"][0]["message"]["content"]
            facts = self._parse_json_array(content)
            for f in facts[:3]:
                self.add(f, kind="fact")
        except Exception:
            pass

    def _parse_json_array(self, s):
        s = (s or "").strip()
        # 去掉可能的 ```json 包裹
        if s.startswith("```"):
            s = s.strip("`")
            if s.lower().startswith("json"):
                s = s[4:]
        lo, hi = s.find("["), s.rfind("]")
        if lo == -1 or hi == -1:
            return []
        try:
            arr = json.loads(s[lo:hi + 1])
            return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            return []
