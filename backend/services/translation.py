import httpx

from services.llm import chat_completion, llm_configured

TRANSLATE_PROMPT = """你是专业译者。请把下面的内容翻译成简体中文，保留原有的段落与列表结构，直接输出译文，不要任何解释或前言。

原文：
{text}"""


async def translate_to_chinese(text: str):
    """翻译为简体中文。优先用已配置的大模型；否则回退 Google 免费翻译接口。"""
    text = (text or "").strip()[:6000]
    if not text:
        return {"translated": "", "engine": "none"}
    if llm_configured():
        try:
            translated = await chat_completion([
                {"role": "system", "content": "你是专业的简体中文译者，译文要通顺自然。"},
                {"role": "user", "content": TRANSLATE_PROMPT.format(text=text)},
            ])
            if translated and translated.strip():
                return {"translated": translated.strip(), "engine": "llm"}
        except Exception:
            pass
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            payload = response.json()
        translated = "".join(seg[0] for seg in payload[0] if seg and seg[0])
        if translated and translated.strip():
            return {"translated": translated.strip(), "engine": "google"}
    except Exception:
        pass
    return {"translated": None, "engine": None}
