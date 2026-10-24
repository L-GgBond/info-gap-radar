import argparse
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, HttpUrl
import uvicorn

from services.article import detect_language, fetch_article
from services.collectors import available_sources, collect_custom_site, collect_items
from services.config import load_settings, providers_meta, save_settings
from services.insights import build_digest, build_report, cluster_events, digest_stats, info_gap_summary, top_info_gap_candidates
from services.llm import analyze_corpus, analyze_item, analyze_item_stream, llm_configured, test_connection
from services.storage import (
    delete_custom_feed,
    delete_custom_site,
    find_custom_feed,
    get_ids_by_urls,
    get_item,
    init_db,
    list_custom_feeds,
    list_custom_sites,
    list_items,
    purge_old_items,
    save_content,
    save_items,
    save_report,
    set_flags,
    upsert_custom_feed,
    upsert_custom_site,
)
from services.translation import translate_to_chinese


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="信息差雷达 API", version="0.4.0", lifespan=lifespan)
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


class FlagsRequest(BaseModel):
    favorite: bool | None = None
    read: bool | None = None
    hidden: bool | None = None


class FeedRequest(BaseModel):
    name: str
    url: HttpUrl
    category: str = "科技"


class SettingsPayload(BaseModel):
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    max_tokens: int | None = None
    cleanup_days: int | None = None
    rsshub_mirror: str | None = None
    watch_keywords: list | None = None
    enabled_sources: list | None = None


def _custom_feeds():
    return [
        {"id": row["id"], "name": row["name"], "url": row["url"], "category": row["category"]}
        for row in list_custom_feeds()
    ]


def _settings_view(settings):
    masked_key = settings.get("api_key", "")
    masked = f"{masked_key[:4]}****{masked_key[-4:]}" if len(masked_key) > 8 else ""
    enabled = settings.get("enabled_sources") or [s["id"] for s in available_sources(_custom_feeds())]
    return {
        "provider": settings["provider"],
        "base_url": settings["base_url"],
        "model": settings["model"],
        "max_tokens": settings.get("max_tokens", 2000),
        "cleanup_days": settings.get("cleanup_days", 180),
        "rsshub_mirror": settings.get("rsshub_mirror", "https://rsshub.app"),
        "watch_keywords": settings.get("watch_keywords") or [],
        "api_key_set": bool(settings["api_key"]),
        "api_key_masked": masked,
        "configured": llm_configured(),
        "enabled_sources": enabled,
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/items")
def items(category: str | None = None, range: str = "all", q: str | None = None,
          favorite: bool = False, limit: int = 500, offset: int = 0):
    return {"items": list_items(category, range, q=q, favorite=favorite,
                                limit=limit, offset=offset)}


@app.get("/items/{item_id}")
def item_detail(item_id: int):
    """完整条目（含正文/翻译/报告），供点开详情时单独拉取。"""
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.patch("/items/{item_id}/flags")
def item_flags(item_id: int, payload: FlagsRequest):
    flags = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not set_flags(item_id, flags):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


@app.post("/crawl")
async def crawl(payload: CrawlRequest):
    settings = load_settings()
    enabled = settings.get("enabled_sources")
    if not enabled:
        enabled = [s["id"] for s in available_sources(_custom_feeds())]
    fresh_items, statuses = await collect_items(
        payload.source, payload.range,
        enabled_sources=set(enabled),
        category=payload.category,
        extra_feeds=_custom_feeds(),
    )
    save_items(fresh_items)
    purged = purge_old_items(settings.get("cleanup_days", 180))
    ok_count = sum(1 for s in statuses if s["ok"])
    prefetch_count = _start_fulltext_prefetch(fresh_items)
    return {
        "saved": len(fresh_items),
        "items": fresh_items,
        "statuses": statuses,
        "ok_sources": ok_count,
        "failed_sources": [s["source"] for s in statuses if not s["ok"]],
        "purged": purged,
        "prefetch": prefetch_count,
    }


# ===== 后台全文预抓 =====

_prefetch_tasks: set = set()


def _start_fulltext_prefetch(fresh_items, cap=24):
    """每源热度 Top3 且未缓存正文的条目，后台预抓全文入库（供 AI 分析直接使用）。"""
    from collections import defaultdict

    by_source = defaultdict(list)
    for it in fresh_items:
        by_source[it.get("source") or "未知"].append(it)
    picks = []
    for _src, group in by_source.items():
        group.sort(key=lambda x: int(x.get("hot_value") or 0), reverse=True)
        picks.extend(group[:3])
    if not picks:
        return 0

    url_map = get_ids_by_urls([it["url"] for it in picks])
    targets = []
    seen = set()
    for it in picks:
        info = url_map.get(it["url"])
        if not info or info["has_content"] or it["url"] in seen:
            continue
        seen.add(it["url"])
        targets.append({"id": info["id"], "url": it["url"]})
    if not targets:
        return 0
    targets = targets[:cap]

    async def run():
        sem = asyncio.Semaphore(3)

        async def one(entry):
            async with sem:
                try:
                    article = await fetch_article(entry["url"])
                    text = (article.get("text") or "").strip()
                    if text:
                        save_content(entry["id"], text, detect_language(text), None, None)
                except Exception:  # noqa: BLE001 - 预抓失败不影响主流程
                    pass

        await asyncio.gather(*(one(t) for t in targets))

    task = asyncio.create_task(run())
    _prefetch_tasks.add(task)
    task.add_done_callback(_prefetch_tasks.discard)
    return len(targets)


@app.get("/sources")
def sources():
    """返回可采集数据源清单（按分类分组，含自定义源标记），供前端渲染来源开关。"""
    raw = available_sources(_custom_feeds())
    groups = {}
    for s in raw:
        groups.setdefault(s["category"], []).append(
            {"id": s["id"], "name": s["name"], "custom": s.get("custom", False)}
        )
    return {
        "groups": [
            {"category": category, "sources": srcs}
            for category, srcs in groups.items()
        ]
    }


# ===== 自定义 RSS 订阅源 =====

@app.get("/feeds")
def feeds_list():
    return {"feeds": list_custom_feeds()}


@app.post("/feeds")
def feeds_add(payload: FeedRequest):
    upsert_custom_feed(payload.name.strip(), str(payload.url), payload.category.strip() or "科技")
    return {"ok": True, "feeds": list_custom_feeds()}


@app.delete("/feeds/{feed_id}")
def feeds_delete(feed_id: int):
    if not delete_custom_feed(feed_id):
        raise HTTPException(status_code=404, detail="Feed not found")
    return {"ok": True, "feeds": list_custom_feeds()}


@app.post("/feeds/import")
async def feeds_import(payload: dict):
    """导入 OPML 文本：{opml: "<xml...>"}，返回导入数量。"""
    from services.collectors import parse_opml
    text = (payload or {}).get("opml") or ""
    if not text.strip():
        raise HTTPException(status_code=400, detail="OPML 内容为空")
    try:
        parsed = parse_opml(text)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"OPML 解析失败：{error}")
    for feed in parsed:
        upsert_custom_feed(feed["name"], feed["url"], feed.get("category") or "科技")
    return {"ok": True, "imported": len(parsed), "feeds": list_custom_feeds()}


@app.get("/feeds/export")
def feeds_export():
    """导出全部内置 + 自定义源为 OPML。"""
    from services.collectors import RSS_SOURCES, export_opml
    all_feeds = [
        {"name": name, "url": url, "category": cat}
        for name, cat, url in RSS_SOURCES
    ] + _custom_feeds()
    xml = export_opml(all_feeds)
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=info-gap-radar.opml"},
    )


# ===== 自定义站点 =====

@app.get("/custom-sites")
def custom_sites_list():
    return {"sites": list_custom_sites()}


@app.delete("/custom-sites/{site_id}")
def custom_sites_delete(site_id: int):
    if not delete_custom_site(site_id):
        raise HTTPException(status_code=404, detail="Site not found")
    return {"ok": True}


@app.post("/crawl/custom")
async def crawl_custom(payload: CustomSiteRequest):
    fresh_items, page_title = await collect_custom_site(str(payload.url))
    upsert_custom_site(str(payload.url), page_title)
    save_items(fresh_items)
    return {"saved": len(fresh_items), "items": fresh_items, "site_title": page_title}


# ===== 条目内容 / 报告 =====

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


@app.post("/items/{item_id}/report/stream")
async def report_stream(item_id: int):
    """流式生成分析报告（SSE 风格的纯文本分块）。未配置大模型时返回 400，前端回退非流式。"""
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not llm_configured():
        raise HTTPException(status_code=400, detail="未配置大模型 API Key")

    async def generate():
        chunks = []
        try:
            async for chunk in analyze_item_stream(item):
                chunks.append(chunk)
                yield chunk
        except Exception as error:  # noqa: BLE001 - 流内错误以正文形式告知前端
            message = f"\n\n> ⚠️ 生成中断：{error}"
            if not chunks:
                message = f"> ⚠️ 大模型调用失败：{error}。请检查 API Key、模型名与网络。"
            yield message
        if chunks:
            save_report(item_id, "".join(chunks))

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


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


@app.get("/settings")
def get_settings():
    return {
        "providers": providers_meta(),
        "settings": _settings_view(load_settings()),
    }


@app.put("/settings")
def put_settings(payload: SettingsPayload):
    saved = save_settings(payload.model_dump(exclude_none=True))
    return {"settings": _settings_view(saved)}


class TestConnPayload(BaseModel):
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@app.post("/settings/test")
async def settings_test(payload: TestConnPayload):
    """用当前（或传入的）配置发一次最小补全请求，验证连通性。"""
    settings = load_settings()
    overrides = payload.model_dump(exclude_none=True)
    for key in ("provider", "api_key", "base_url", "model"):
        if overrides.get(key):
            settings[key] = overrides[key]
    try:
        result = await test_connection(settings)
        return result
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"连接失败：{error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, reload=False)
