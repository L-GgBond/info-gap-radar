import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".info-gap-radar" / "config.json"

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
}


def load_settings():
    settings = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                for key in DEFAULTS:
                    if key in stored:
                        settings[key] = stored[key]
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(payload):
    settings = load_settings()
    for key in DEFAULTS:
        value = payload.get(key)
        if value is not None:
            settings[key] = str(value).strip()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return settings


def providers_meta():
    return [{"id": key, **meta} for key, meta in PROVIDERS.items()]
