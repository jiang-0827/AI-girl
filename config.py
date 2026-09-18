"""配置管理模块 - 负责 config.json 的读写"""
import json
import os
from utils.resource_path import config_path, resource_path

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "qwen-turbo",
    "system_prompt": "你是一个可爱的桌面小助手，说话简洁、活泼、有温度，回答尽量简短（每次不超过120字）。",
    "character_image": "assets/character.png",
    "pet_size": 176,
    "pet_size_min": 100,
    "pet_size_max": 360,
    "opacity": 255,
    "hotkey": "<ctrl>+<shift>+<space>",
    "enable_tts": True,
    "tts_voice": "Cherry",
    "enable_asr": True,
    "voice_hotkey": "<ctrl>+<shift>+v",
    "enable_tools": True,
    "enable_memory": True,
    "memory_topk": 4,
    "proactive_enabled": True,
    "proactive_idle_min": 30,
    "proactive_hourly": False,
    "proactive_sit_enabled": False,
    "proactive_sit_min": 60,
    "position_x": -1,
    "position_y": -1,
    "position_set": False,
    "auto_start": False,
    "first_run": True,
    # 互动体验（桌宠增强）
    "follow_mouse": False,      # 跟随鼠标
    "always_on_top": True,      # 始终置顶
    "interactive": True,        # 点击轮流互动
    "random_chatter": True,     # 闲时随机气泡
}


def load_config() -> dict:
    """加载配置，若不存在则创建默认"""
    path = config_path()
    if not os.path.exists(path):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    """保存配置到 JSON"""
    path = config_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存配置失败: {e}")


def update_config(**kwargs) -> dict:
    """更新配置项并保存"""
    cfg = load_config()
    cfg.update(kwargs)
    save_config(cfg)
    return cfg


def get_image_path(cfg: dict) -> str:
    """获取角色图片的绝对路径"""
    img = cfg.get('character_image', 'assets/character.png')
    if os.path.isabs(img):
        return img
    return resource_path(img)
