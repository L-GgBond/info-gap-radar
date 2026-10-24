import json
import os
from pathlib import Path

# 支持用环境变量隔离数据目录（测试/多实例），默认在用户主目录
APP_DIR = Path(os.environ.get("INFO_GAP_HOME", str(Path.home() / ".info-gap-radar")))
CONFIG_PATH = APP_DIR / "config.json"

PROVIDERS = {
    "dashscope": {
        "label": "通义千问（DashScope）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "custom": {
        "label": "自定义（OpenAI 兼容接口）",
        "base_url": "",
        "default_model": "",
    },
}

DEFAULTS = {
    "provider": "dashscope",
    "api_key": "",
    "base_url": PROVIDERS["dashscope"]["base_url"],
    "model": PROVIDERS["dashscope"]["default_model"],
    "max_tokens": 2000,
    "cleanup_days": 180,
    "rsshub_mirror": "https://rsshub.app",
}

# 列表型设置项（不做 str() 转换，整体覆盖）
LIST_KEYS = ("enabled_sources", "watch_keywords")


def load_settings():
    settings = dict(DEFAULTS)
    settings["watch_keywords"] = []
    if CONFIG_PATH.exists():
        try:
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                for key in DEFAULTS:
                    if key in stored:
                        settings[key] = stored[key]
                for key in LIST_KEYS:
                    if isinstance(stored.get(key), list):
                        settings[key] = stored[key]
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(payload):
    settings = load_settings()
    for key in DEFAULTS:
        value = payload.get(key)
        if value is not None and value != "":
            try:
                settings[key] = int(value) if key in ("max_tokens", "cleanup_days") else str(value).strip()
            except (TypeError, ValueError):
                settings[key] = str(value).strip()
    # 显式传空字符串视为清空（如清除 API Key 的场景不做，Key 留空=不修改）
    for key in ("provider", "base_url", "model"):
        value = payload.get(key)
        if value is not None and str(value).strip() == "" and key != "base_url":
            settings[key] = str(value).strip()
    for key in LIST_KEYS:
        if isinstance(payload.get(key), list):
            cleaned = [str(v).strip() for v in payload[key] if str(v).strip()]
            settings[key] = cleaned
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return settings


def providers_meta():
    return [{"id": key, **meta} for key, meta in PROVIDERS.items()]
