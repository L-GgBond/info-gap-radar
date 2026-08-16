import argparse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import uvicorn

from services.article import detect_language, fetch_article
from services.collectors import collect_custom_site, collect_items
from services.config import load_settings, providers_meta, save_settings
from services.insights import build_report
from services.llm import analyze_item, llm_configured
from services.storage import (
    get_item,
    init_db,
    list_items,
    save_content,
    save_items,
    save_report,
)
from services.translation import translate_to_chinese


app = FastAPI(title="信息差雷达 API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CrawlRequest(BaseModel):
    source: str = "all"
    range: str = "all"


class CustomSiteRequest(BaseModel):
    url: HttpUrl


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/items")
def items(category: str | None = None, range: str = "all"):
    return {"items": list_items(category, range)}


@app.post("/crawl")
async def crawl(payload: CrawlRequest):
    fresh_items = await collect_items(payload.source, payload.range)
    save_items(fresh_items)
    return {"saved": len(fresh_items), "items": fresh_items}


@app.post("/crawl/custom")
async def crawl_custom(payload: CustomSiteRequest):
    fresh_items = await collect_custom_site(str(payload.url))
    save_items(fresh_items)
    return {"saved": len(fresh_items), "items": fresh_items}


@app.get("/items/{item_id}/content")
async def item_content(item_id: int):
    """抓取并返回原文；非中文内容附带中文翻译。结果按条目缓存。"""
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.get("content"):
        return {
            "url": item["url"],
            "title": item.get("title"),
            "content": item["content"],
            "language": item.get("language"),
            "translated": item.get("translated"),
            "translation_engine": item.get("translation_engine"),
            "cached": True,
        }
    # 尝试实时抓取原文；失败或返回空时回退到本地摘要，不直接报错
    fallback_reason = None
    fetched_text = None
    fetched_title = None
    try:
        article = await fetch_article(item["url"])
        fetched_text = article.get("text") or ""
        fetched_title = article.get("title")
    except Exception as error:  # noqa: BLE001 - 统一降级，不抛 502
        fallback_reason = f"原文抓取失败：{error}"
    if fetched_text:
        text = fetched_text
    else:
        if not fallback_reason:
            fallback_reason = "原文抓取未返回正文，已展示本地摘要"
        text = item.get("summary") or item.get("raw_text") or "（暂无可用内容）"
    language = detect_language(text)
    translated, engine = None, None
    if language != "zh":
        try:
            result = await translate_to_chinese(text)
            translated, engine = result["translated"], result["engine"]
        except Exception:  # noqa: BLE001 - 翻译失败不阻断原文展示
            translated, engine = None, None
    # 仅当真正抓到原文时才写库缓存，避免把摘要误存为原文
    if fetched_text and not item.get("content"):
        save_content(item_id, text, language, translated, engine)
    return {
        "url": item["url"],
        "title": fetched_title or item.get("title"),
        "content": text,
        "language": language,
        "translated": translated,
        "translation_engine": engine,
        "cached": False,
        "fallback": bool(fallback_reason),
        "fallback_reason": fallback_reason,
    }


@app.post("/items/{item_id}/report")
async def report(item_id: int):
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if llm_configured():
        try:
            markdown = await analyze_item(item)
        except Exception as error:  # noqa: BLE001 - 统一转成前端可读的中文错误
            raise HTTPException(
                status_code=502,
                detail=f"大模型调用失败：{error}。请检查 API Key、模型名与网络，或到设置里切换服务商。",
            )
        engine = "llm"
    else:
        markdown = build_report(item)
        engine = "local"
    save_report(item_id, markdown)
    return {"report": markdown, "engine": engine}


class SettingsPayload(BaseModel):
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@app.get("/settings")
def get_settings():
    settings = load_settings()
    masked_key = settings.get("api_key", "")
    masked = f"{masked_key[:4]}****{masked_key[-4:]}" if len(masked_key) > 8 else ""
    return {
        "providers": providers_meta(),
        "settings": {
            "provider": settings["provider"],
            "base_url": settings["base_url"],
            "model": settings["model"],
            "api_key_set": bool(settings["api_key"]),
            "api_key_masked": masked,
            "configured": llm_configured(),
        },
    }


@app.put("/settings")
def put_settings(payload: SettingsPayload):
    saved = save_settings(payload.model_dump(exclude_none=True))
    masked_key = saved.get("api_key", "")
    masked = f"{masked_key[:4]}****{masked_key[-4:]}" if len(masked_key) > 8 else ""
    return {
        "settings": {
            "provider": saved["provider"],
            "base_url": saved["base_url"],
            "model": saved["model"],
            "api_key_set": bool(saved["api_key"]),
            "api_key_masked": masked,
            "configured": llm_configured(),
        }
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run("main:app", host="127.0.0.1", port=args.port, reload=False)
