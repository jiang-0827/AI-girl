"""系统操作工具集 - 供 AI function calling 调用
每个工具：SCHEMAS 里定义 OpenAI 兼容 schema；run() 执行；is_dangerous() 判断是否需确认。
所有工具返回给模型的是简短字符串结果。ctx 提供 add_reminder 等回调。
"""
import os
import json
import glob
import datetime
import subprocess

# ---------- 可选依赖，缺失时优雅降级 ----------
try:
    import psutil
    _PSUTIL = True
except Exception:
    _PSUTIL = False

try:
    import pygetwindow as gw
    _PYGETWINDOW = True
except Exception:
    _PYGETWINDOW = False


# ================= 应用/文件 =================
def _app_paths():
    """枚举注册表 App Paths + 开始菜单快捷方式，返回 {显示名: 可执行路径/lnk}"""
    found = {}
    # 注册表 App Paths
    try:
        import winreg
        roots = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
        subkeys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ]
        for root in roots:
            for sk in subkeys:
                try:
                    key = winreg.OpenKey(root, sk)
                except OSError:
                    continue
                try:
                    i = 0
                    while True:
                        try:
                            exe_name = winreg.EnumKey(key, i)
                        except OSError:
                            break
                        try:
                            ek = winreg.OpenKey(key, exe_name)
                            path, _ = winreg.QueryValueEx(ek, "")
                            found[os.path.splitext(exe_name)[0]] = path
                        except OSError:
                            pass
                        i += 1
                finally:
                    winreg.CloseKey(key)
    except Exception:
        pass
    # 开始菜单快捷方式
    menus = [
        os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
    ]
    for m in menus:
        if not m or not os.path.isdir(m):
            continue
        for lnk in glob.glob(os.path.join(m, "**", "*.lnk"), recursive=True):
            name = os.path.splitext(os.path.basename(lnk))[0]
            if name.lower() in ("uninstall", "卸载") or "uninstall" in name.lower():
                continue
            found.setdefault(name, lnk)
    return found


def open_app(args, ctx):
    name = (args.get("name") or "").strip()
    if not name:
        return "未提供应用名"
    apps = ctx.get("apps") or _app_paths()
    ctx["apps"] = apps
    low = name.lower()
    # 精确/包含匹配
    cands = [(k, v) for k, v in apps.items() if low == k.lower()]
    if not cands:
        cands = [(k, v) for k, v in apps.items() if low in k.lower() or k.lower() in low]
    if not cands:
        return f"没找到名为「{name}」的应用"
    disp, target = cands[0]
    try:
        os.startfile(target)
        return f"已打开：{disp}"
    except Exception as e:
        return f"打开 {disp} 失败：{e}"


def open_file(args, ctx):
    path = (args.get("path") or "").strip()
    if not path or not os.path.exists(path):
        return f"路径不存在：{path}"
    try:
        os.startfile(path)
        return f"已打开：{os.path.basename(path)}"
    except Exception as e:
        return f"打开失败：{e}"


def create_file(args, ctx):
    """创建文本文件（记事本文件）。默认在桌面，可指定文档/下载。"""
    name = (args.get("name") or "新建文档").strip()
    content = args.get("content") or ""
    loc = (args.get("location") or "desktop").lower()
    # 安全：文件名不允许路径分隔符和危险字符
    name = name.replace("/", "_").replace("\\", "_").replace(":", "_").replace("..", "")
    if not name.lower().endswith(".txt"):
        name += ".txt"
    base_map = {
        "desktop": os.path.expanduser("~\\Desktop"),
        "\u684c\u9762": os.path.expanduser("~\\Desktop"),
        "documents": os.path.expanduser("~\\Documents"),
        "\u6587\u6863": os.path.expanduser("~\\Documents"),
        "downloads": os.path.expanduser("~\\Downloads"),
        "\u4e0b\u8f7d": os.path.expanduser("~\\Downloads"),
    }
    base = base_map.get(loc, os.path.expanduser("~\\Desktop"))
    path = os.path.join(base, name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        # 可选自动打开
        if args.get("open", False):
            os.startfile(path)
        return f"已创建文件：{path}"
    except Exception as e:
        return f"创建文件失败：{e}"


def search_file(args, ctx):
    kw = (args.get("keyword") or "").strip()
    if not kw:
        return "未提供关键词"
    roots = [
        os.path.expanduser("~\\Desktop"),
        os.path.expanduser("~\\Documents"),
        os.path.expanduser("~\\Downloads"),
    ]
    results = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            # 限制深度
            if dirpath[len(root):].count(os.sep) > 3:
                dirs[:] = []
                continue
            for fn in files:
                if kw.lower() in fn.lower():
                    results.append(os.path.join(dirpath, fn))
                    if len(results) >= 15:
                        break
            if len(results) >= 15:
                break
        if len(results) >= 15:
            break
    if not results:
        return f"在桌面/文档/下载里没找到含「{kw}」的文件"
    return "找到文件：\n" + "\n".join(results[:15])


# ================= 音量 =================
def _get_volume_obj():
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def set_volume(args, ctx):
    pct = max(0, min(100, int(args.get("percent", 50))))
    try:
        vol = _get_volume_obj()
        vol.SetMasterVolumeLevelScalar(pct / 100.0, None)
        return f"音量已调到 {pct}%"
    except Exception as e:
        return f"调节音量失败（可能缺 pycaw 或无音频设备）：{e}"


def get_volume(args, ctx):
    try:
        vol = _get_volume_obj()
        scalar = vol.GetMasterVolumeLevelScalar()
        return f"当前音量约 {int(round(scalar * 100))}%"
    except Exception as e:
        return f"读取音量失败：{e}"


# ================= 亮度 =================
def set_brightness(args, ctx):
    pct = max(0, min(100, int(args.get("percent", 50))))
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(pct)
        return f"屏幕亮度已调到 {pct}%"
    except Exception as e:
        return f"调节亮度失败（台式机/外接显示器常不支持软件调光）：{e}"


# ================= 窗口 =================
def list_windows(args, ctx):
    if not _PYGETWINDOW:
        return "窗口管理库未安装"
    try:
        titles = [t for t in gw.getAllTitles() if t.strip()]
        return "当前打开的窗口：\n" + "\n".join(titles[:30])
    except Exception as e:
        return f"获取窗口失败：{e}"


def focus_window(args, ctx):
    if not _PYGETWINDOW:
        return "窗口管理库未安装"
    title = (args.get("title") or "").strip()
    for w in gw.getAllWindows():
        if title.lower() in (w.title or "").lower():
            try:
                w.restore()
                w.activate()
                return f"已切换到窗口：{w.title}"
            except Exception as e:
                return f"切换失败：{e}"
    return f"没找到标题含「{title}」的窗口"


def close_window(args, ctx):
    if not _PYGETWINDOW:
        return "窗口管理库未安装"
    title = (args.get("title") or "").strip()
    for w in gw.getAllWindows():
        if title.lower() in (w.title or "").lower():
            try:
                w.close()
                return f"已关闭窗口：{w.title}"
            except Exception as e:
                return f"关闭失败：{e}"
    return f"没找到标题含「{title}」的窗口"


# ================= 系统信息 / 时间 =================
def system_status(args, ctx):
    if not _PSUTIL:
        return "系统信息库未安装"
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory().percent
    bat = psutil.sensors_battery()
    bat_txt = f"，电池 {int(bat.percent)}%{'(充电中)' if bat.power_plugged else ''}" if bat else ""
    return f"CPU {cpu:.0f}%，内存 {mem:.0f}%{bat_txt}"


def get_datetime(args, ctx):
    now = datetime.datetime.now()
    week = "一二三四五六日"[now.weekday()]
    return f"现在是 {now.strftime('%Y-%m-%d %H:%M')} 星期{week}"


# ================= 提醒（交给 ctx 调度器） =================
def create_reminder(args, ctx):
    seconds = int(args.get("seconds", 0))
    text = (args.get("text") or "").strip()
    if seconds <= 0 or not text:
        return "需要提醒时间(秒)和内容"
    if "add_reminder" not in ctx:
        return "提醒功能未启用"
    rid = ctx["add_reminder"](seconds, text)
    if seconds >= 3600:
        span = f"{seconds/3600:.1f} 小时后"
    elif seconds >= 60:
        span = f"{seconds//60} 分钟后"
    else:
        span = f"{seconds} 秒后"
    return f"好的，{span}提醒你：{text}"


def list_reminders(args, ctx):
    if "list_reminders" not in ctx:
        return "提醒功能未启用"
    items = ctx["list_reminders"]()
    if not items:
        return "目前没有待办提醒"
    return "待办提醒：\n" + "\n".join(items)


def cancel_reminder(args, ctx):
    if "cancel_reminder" not in ctx:
        return "提醒功能未启用"
    rid = int(args.get("id", -1))
    return ctx["cancel_reminder"](rid)


# ================= schema =================
SCHEMAS = [
    {"type": "function", "function": {
        "name": "open_app", "description": "打开/启动一个电脑应用程序，如微信、浏览器、记事本",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "应用名称或关键词"}}, "required": ["name"]}}},
    {"type": "function", "description": "", "function": {
        "name": "open_file", "description": "按完整路径打开一个文件或文件夹",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "search_file", "description": "在桌面/文档/下载中按关键词搜索文件",
        "parameters": {"type": "object", "properties": {
            "keyword": {"type": "string"}}, "required": ["keyword"]}}},
    {"type": "function", "function": {
        "name": "set_volume", "description": "把系统主音量设置为指定百分比(0-100)",
        "parameters": {"type": "object", "properties": {
            "percent": {"type": "integer"}}, "required": ["percent"]}}},
    {"type": "function", "function": {
        "name": "get_volume", "description": "查询当前系统音量", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "set_brightness", "description": "把屏幕亮度设置为指定百分比(0-100)",
        "parameters": {"type": "object", "properties": {
            "percent": {"type": "integer"}}, "required": ["percent"]}}},
    {"type": "function", "function": {
        "name": "list_windows", "description": "列出当前打开的所有窗口", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "focus_window", "description": "切换/前置到某个窗口",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"}}, "required": ["title"]}}},
    {"type": "function", "function": {
        "name": "close_window", "description": "关闭某个窗口（可能丢失未保存内容）",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"}}, "required": ["title"]}}},
    {"type": "function", "function": {
        "name": "system_status", "description": "查看CPU/内存/电量等系统状态", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_datetime", "description": "获取当前日期和时间", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "create_reminder", "description": "创建一条定时提醒。把用户说的时间换算成秒，如'10分钟后'=600",
        "parameters": {"type": "object", "properties": {
            "seconds": {"type": "integer", "description": "多少秒后提醒"},
            "text": {"type": "string", "description": "提醒内容"}}, "required": ["seconds", "text"]}}},
    {"type": "function", "function": {
        "name": "list_reminders", "description": "列出所有待办提醒", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "cancel_reminder", "description": "取消某条提醒(按id)",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "integer"}}, "required": ["id"]}}},
    {"type": "function", "function": {
        "name": "create_file", "description": "创建一个文本文件(记事本)，可指定内容和位置(desktop/documents/downloads)",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "文件名(不含路径)"},
            "content": {"type": "string", "description": "文件内容"},
            "location": {"type": "string", "enum": ["desktop", "documents", "downloads"], "description": "保存位置，默认desktop"},
            "open": {"type": "boolean", "description": "创建后是否自动打开"}}, "required": ["name"]}}},
]

_IMPL = {
    "open_app": open_app, "open_file": open_file, "search_file": search_file,
    "create_file": create_file,
    "set_volume": set_volume, "get_volume": get_volume, "set_brightness": set_brightness,
    "list_windows": list_windows, "focus_window": focus_window, "close_window": close_window,
    "system_status": system_status, "get_datetime": get_datetime,
    "create_reminder": create_reminder, "list_reminders": list_reminders, "cancel_reminder": cancel_reminder,
}

# 需要“每次弹窗确认”才执行的操作（会改动电脑/系统或涉及隐私）
CONFIRM_REQUIRED = {
    "open_app", "open_file", "search_file", "create_file",
    "set_volume", "set_brightness",
    "focus_window", "close_window",
}

# 绝对禁止的关键词（对电脑有害的操作），命中即拒绝执行，不确认、不运行
_FORBIDDEN_KEYWORDS = [
    "shutdown", "restart", "reboot", "logoff", "format", "diskpart", "cipher",
    "taskkill", "reg delete", "rd /s", "rmdir", "del ", "delete", "remove-item",
    "关机", "重启", "格式化", "删除", "卸载", "清空", "回收站", "注册表",
]


def is_forbidden(name, args):
    """判断某次调用是否触及禁止的有害操作，返回 (bool, reason)"""
    try:
        blob = ((name or "") + " " + json.dumps(args or {}, ensure_ascii=False)).lower()
    except Exception:
        blob = str(name).lower()
    for kw in _FORBIDDEN_KEYWORDS:
        if kw.lower() in blob:
            return True, f"该操作涉及被禁止的高风险行为（{kw}），出于安全我不能执行。"
    return False, ""


def run(name, args, ctx):
    fn = _IMPL.get(name)
    if not fn:
        return f"未知工具：{name}"
    forbidden, reason = is_forbidden(name, args)
    if forbidden:
        return reason
    try:
        return fn(args or {}, ctx)
    except Exception as e:
        return f"执行 {name} 出错：{e}"


def needs_confirm(name):
    """是否需要每次确认"""
    return name in CONFIRM_REQUIRED


def describe(name, args):
    args = args or {}
    return {
        "open_app": f"打开应用「{args.get('name','')}」",
        "open_file": f"打开文件 {args.get('path','')}",
        "search_file": f"搜索文件「{args.get('keyword','')}」",
        "set_volume": f"设置音量为 {args.get('percent','')}%",
        "get_volume": "查询音量",
        "set_brightness": f"设置亮度为 {args.get('percent','')}%",
        "list_windows": "列出窗口",
        "focus_window": f"切换到窗口「{args.get('title','')}」",
        "close_window": f"关闭窗口「{args.get('title','')}」",
        "system_status": "查看系统状态",
        "get_datetime": "查看时间",
        "create_reminder": f"{args.get('seconds','')}秒后提醒：{args.get('text','')}",
        "list_reminders": "查看提醒列表",
        "cancel_reminder": f"取消提醒 #{args.get('id','')}",
        "create_file": f"创建文件「{args.get('name','')}」", 
    }.get(name, name)
