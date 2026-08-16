import argparse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import uvicorn

from services.article import detect_language, fetch_article
from services.collectors import available_sources, collect_custom_site, collect_items
from services.config import load_settings, providers_meta, save_settings
from services.insights import build_digest, build_report, cluster_events, digest_stats, info_gap_summary, top_info_gap_candidates
from services.llm import analyze_corpus, analyze_item, llm_configured
from services.storage import (
    get_item,
    init_db,
    list_items,
    save_content,
    save_items,
    save_report,
)
from services.translation import translate_to_chinese


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="信息差雷达 API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CrawlRequest(BaseModel):
    source: str = "all"
    range: str = "all"
    category: str | None = None


class CustomSiteRequest(BaseModel):
    url: HttpUrl


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/items")
def items(category: str | None = None, range: str = "all"):
    return {"items": list_items(category, range)}


@app.post("/crawl")
async def crawl(payload: CrawlRequest):
    settings = load_settings()
    enabled = settings.get("enabled_sources")
    if not enabled:
        enabled = [s["id"] for s in available_sources()]
    fresh_items = await collect_items(payload.source, payload.range, enabled_sources=set(enabled), category=payload.category)
    save_items(fresh_items)
    return {"saved": len(fresh_items), "items": fresh_items}


@app.get("/sources")
def sources():
    """返回可采集数据源清单（按分类分组），供前端渲染来源开关。"""
    raw = available_sources()
    groups = {}
    for s in raw:
        groups.setdefault(s["category"], []).append({"id": s["id"], "name": s["name"]})
    return {
        "groups": [
            {"category": category, "sources": srcs}
            for category, srcs in groups.items()
        ]
    }


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


class ReportRequest(BaseModel):
    category: str = "全部"
    range: str = "all"


@app.post("/report")
async def global_report(payload: ReportRequest):
    items = list_items(payload.category, payload.range)
    if llm_configured():
        try:
            markdown = await analyze_corpus(items, payload.category, payload.range)
            engine = "llm"
        except Exception as error:  # noqa: BLE001 - 失败时回退本地聚合，不让前端报错
            markdown = build_digest(items, payload.category, payload.range)
            engine = "local"
            markdown += f"\n\n> 提示：大模型调用失败（{error}），以上为本地聚合结果。"
    else:
        markdown = build_digest(items, payload.category, payload.range)
        engine = "local"
    return {
        "report": markdown,
        "engine": engine,
        "stats": digest_stats(items, payload.category, payload.range),
        "candidates": top_info_gap_candidates(items, limit=30),
        "total": len(items),
    }


@app.get("/insight/summary")
def insight_summary():
    items = list_items("全部", "all")
    return info_gap_summary(items)


@app.get("/clusters")
def clusters(category: str = "全部", range: str = "all"):
    """跨源事件聚类：把同一事件的多源报道合并，标注境内外分布并量化信息差分。"""
    items = list_items(category, range)
    return {"clusters": cluster_events(items), "total": len(items)}


class SettingsPayload(BaseModel):
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    enabled_sources: list | None = None


@app.get("/settings")
def get_settings():
    settings = load_settings()
    masked_key = settings.get("api_key", "")
    masked = f"{masked_key[:4]}****{masked_key[-4:]}" if len(masked_key) > 8 else ""
    enabled = settings.get("enabled_sources") or [s["id"] for s in available_sources()]
    return {
        "providers": providers_meta(),
        "settings": {
            "provider": settings["provider"],
            "base_url": settings["base_url"],
            "model": settings["model"],
            "api_key_set": bool(settings["api_key"]),
            "api_key_masked": masked,
            "configured": llm_configured(),
            "enabled_sources": enabled,
        },
    }


@app.put("/settings")
def put_settings(payload: SettingsPayload):
    saved = save_settings(payload.model_dump(exclude_none=True))
    masked_key = saved.get("api_key", "")
    masked = f"{masked_key[:4]}****{masked_key[-4:]}" if len(masked_key) > 8 else ""
    enabled = saved.get("enabled_sources") or [s["id"] for s in available_sources()]
    return {
        "settings": {
            "provider": saved["provider"],
            "base_url": saved["base_url"],
            "model": saved["model"],
            "api_key_set": bool(saved["api_key"]),
            "api_key_masked": masked,
            "configured": llm_configured(),
            "enabled_sources": enabled,
        }
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, reload=False)
