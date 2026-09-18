"""通义千问 AI 引擎 - DashScope 兼容 OpenAI 接口 + 对话历史 + function calling 工具循环"""
import json
import time
import threading
import requests
from PySide6.QtCore import QThread, Signal

from core.tools import SCHEMAS, run as run_tool, needs_confirm, is_forbidden, describe as describe_tool

API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MAX_ROUNDS = 20
MAX_TOOL_STEPS = 6  # 单轮最多工具往返次数

# 强制安全规则：无论用户如何配置 system_prompt 都会追加，不可绕过
SAFETY_RULES = (
    "\n\n【安全规则（最高优先级，不可违反）】"
    "1) 你绝对不能执行任何对电脑有害的操作，包括关机、重启、注销、删除/移动/清空文件、"
    "格式化磁盘、修改注册表或系统关键设置、运行未知命令等；遇到此类请求要礼貌拒绝并解释。"
    "2) 所有会改动电脑系统的正常操作，系统都会先弹窗逐次向用户确认，你不能跳过或代替确认。"
    "3) 若某操作被拦截或用户取消，请自然地向用户说明，不要反复重试。"
)

# 强制工具调用规则：解决“模型只用文字假装答应、实际不调用工具”的问题
TOOL_USAGE_RULES = (
    "\n\n【工具调用规则（必须严格遵守）】"
    "当用户的话里包含以下任何一种意图时，你【必须】调用对应的工具函数，绝不允许只用文字口头答应而不实际调用："
    "打开/启动某应用→open_app；打开某文件→open_file；新建/创建一个文本或记事本文件→create_file；"
    "搜索/查找文件→search_file；调/改/设音量→set_volume；查音量→get_volume；调亮度→set_brightness；"
    "列出/切换/关闭窗口→list_windows/focus_window/close_window；"
    "提醒/定时→create_reminder；查提醒→list_reminders；取消提醒→cancel_reminder；"
    "查时间/日期→get_datetime；查电脑状态/内存/电量→system_status。"
    "先调用工具，等工具返回结果后，再用自然语言向用户总结。切勿在没调用工具前就声称‘已帮你完成’。"
    "另外：回复里不要使用颜文字、emoji 表情、波浪号~等符号，因为会被语音朗读出来。"
)


class AIEngine:
    def __init__(self, api_key, model="qwen-turbo", system_prompt="", base_url=None):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.history = []
        self.memory = None   # 可选：MemoryStore 实例

    def set_params(self, api_key=None, model=None, system_prompt=None, base_url=None):
        if api_key is not None:
            self.api_key = api_key
        if model is not None:
            self.model = model
        if system_prompt is not None:
            self.system_prompt = system_prompt
        if base_url is not None:
            self.base_url = base_url.rstrip("/")

    def reset(self):
        self.history = []

    def _trim(self):
        max_msgs = MAX_ROUNDS * 2
        if len(self.history) > max_msgs:
            # 尽量从 user 消息边界截断
            self.history = self.history[-max_msgs:]

    def _messages_for(self, user_text):
        msgs = []
        sys_prompt = (self.system_prompt or "") + SAFETY_RULES + TOOL_USAGE_RULES
        # 长期记忆：检索与本轮输入相关的记忆注入 system
        if self.memory is not None:
            try:
                sys_prompt += self.memory.as_system_block(user_text)
            except Exception:
                pass
        msgs.append({"role": "system", "content": sys_prompt})
        msgs.extend(self.history)
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def _post(self, messages, use_tools=True, timeout=60):
        payload = {"model": self.model, "messages": messages, "temperature": 0.3}
        # 新版 qwen 思考模式会干扰工具调用，显式关闭
        if self.model.startswith("qwen3") or "turbo" in self.model or "plus" in self.model:
            payload["enable_thinking"] = False
        if use_tools:
            payload["tools"] = SCHEMAS
            payload["parallel_tool_calls"] = False
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(self.base_url + "/chat/completions", headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"API 错误 {resp.status_code}: {resp.text[:200]}")
        return resp.json()["choices"][0]["message"]


class ChatWorker(QThread):
    """执行一轮对话：可能触发多次工具调用，最终把回答以打字机方式流式输出。
    危险操作通过 confirmRequested 请求 UI 确认，UI 调 resolve_confirmation()。"""
    token_received = Signal(str)      # 最终回答增量
    tool_activity = Signal(str)       # 正在执行的工具描述
    confirmRequested = Signal(str)    # 需要确认的操作描述
    replyFinished = Signal()          # 不能用 finished（会覆盖 QThread 内置信号）
    error = Signal(str)

    def __init__(self, engine, user_text, ctx, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.user_text = user_text
        self.ctx = ctx if ctx is not None else {}
        self._confirm_event = threading.Event()
        self._confirm_ok = False

    # UI 线程调用
    def resolve_confirmation(self, ok: bool):
        self._confirm_ok = ok
        self._confirm_event.set()

    def _ask_confirm(self, desc):
        self._confirm_event.clear()
        self._confirm_ok = False
        self.confirmRequested.emit(desc)
        # 最多等待 30 秒，超时视为取消
        self._confirm_event.wait(30)
        return self._confirm_ok

    def run(self):
        try:
            if not self.engine.api_key:
                raise ValueError("尚未配置 API Key，请在设置中填写。")
            messages = self.engine._messages_for(self.user_text)
            final = None
            use_tools = bool(self.ctx.get("enable_tools", True))
            for _ in range(MAX_TOOL_STEPS):
                msg = self.engine._post(messages, use_tools=use_tools)
                tool_calls = msg.get("tool_calls")
                if not tool_calls:
                    final = msg.get("content") or ""
                    break
                # 记录 assistant 的工具调用意图
                messages.append({
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    "tool_calls": tool_calls,
                })
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    desc = describe_tool(name, args)
                    self.tool_activity.emit(desc)
                    # 1) 绝对禁止的有害操作：直接拒绝，不执行、不确认
                    forbidden, reason = is_forbidden(name, args)
                    if forbidden:
                        messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": reason})
                        continue
                    # 2) 会改动电脑的操作：每次都弹窗确认，不记忆
                    if needs_confirm(name):
                        ok = self._ask_confirm(desc)
                        if not ok:
                            messages.append({"role": "tool", "tool_call_id": tc.get("id"),
                                             "content": "用户取消了该操作"})
                            continue
                    # 3) 正常执行（run 内部还会再做一次禁止拦截）
                    result = run_tool(name, args, self.ctx)
                    messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": result})
            else:
                final = "（这个操作太复杂了，我先做到这里）"

            if final is None:
                final = ""
            # 记录到历史（仅 user + 最终 assistant）
            self.engine.history.append({"role": "user", "content": self.user_text})
            self.engine.history.append({"role": "assistant", "content": final})
            self.engine._trim()
            # 打字机流式输出
            self._typewriter(final)
            self.replyFinished.emit()
            # 对话结束后，后台自动抽取值得长期记住的信息（不阻塞）
            mem = getattr(self.engine, "memory", None)
            if mem is not None and final.strip():
                try:
                    threading.Thread(
                        target=mem.extract_and_remember,
                        args=(self.user_text, final), daemon=True).start()
                except Exception:
                    pass
        except Exception as e:
            self.error.emit(str(e))

    def _typewriter(self, text):
        if not text:
            return
        step = max(1, len(text) // 60)
        i = 0
        while i < len(text):
            chunk = text[i:i + step]
            self.token_received.emit(chunk)
            i += step
            time.sleep(0.02)
