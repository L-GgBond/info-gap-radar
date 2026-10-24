import asyncio
import json

import httpx

from services.config import load_settings

PROMPT_TEMPLATE = """你是信息差分析师，基于下面的热点条目信息，生成一份简洁的中文分析报告。

条目信息：
- 标题：{title}
- 来源：{source}
- 分类：{category}
- 热度分：{hot_score}/100（原始热度 {hot_value}）
- 摘要：{summary}
{fulltext_section}
报告需要包含下面模块（使用 markdown 格式，直接输出正文，不要废话）：
1. ## 核心简述：这件事/这个项目到底是什么
2. ## 热点原因：为什么它现在热度高（如信息不足，可基于领域常识合理推断并注明）
3. ## 价值信息：可以学到什么、有什么用处、适合谁
4. ## 潜在风险：可能的缺点、坑或风险
5. ## 延伸洞察：普通人可以获得什么信息差、可以采取的行动

输出 markdown 格式。"""

CORPUS_PROMPT = """你是信息差分析师。下面是一批已采集的热点条目（按分类聚合，仅保留每条的标题、来源、分类与热度分）。
请基于这些信息，生成一份中文「信息差洞察」报告，目标是帮助读者发现：哪些话题在境外/技术圈已经很热、但在中文普通读者中尚未充分覆盖（即信息差），以及值得普通人关注和行动的信号。

条目数据：
{data}

请输出 markdown 格式，包含以下模块（直接输出正文，不要废话）：
1. ## 总体态势：这批热点反映的大趋势
2. ## 信息差机会：境外/技术圈已热、中文世界尚冷的具体话题（给出 3-6 条，每条点名条目并说明为什么是信息差）
3. ## 值得跟进的信号：最可能持续发酵或影响普通人的方向
4. ## 行动建议：普通人可以怎么利用这些信息差（学习、投资、副业、避坑等）

输出 markdown 格式。"""

# 拼入 prompt 的全文上限（字符）；正文更长时截断，避免 token 爆炸
FULLTEXT_LIMIT = 8000
RETRY_ATTEMPTS = 3
RETRY_STATUS = (429, 500, 502, 503, 504)


def llm_configured():
    settings = load_settings()
    return bool(settings.get("api_key") and settings.get("base_url") and settings.get("model"))


def _headers(settings):
    return {"Authorization": f"Bearer {settings['api_key']}"}


def _payload(messages, settings, stream=False):
    return {
        "model": settings["model"],
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": int(settings.get("max_tokens") or 2000),
        "stream": stream,
    }


async def chat_completion(messages, settings=None):
    """非流式补全，带 429/5xx 指数退避重试。"""
    settings = settings or load_settings()
    url = settings["base_url"].rstrip("/") + "/chat/completions"
    payload = _payload(messages, settings, stream=False)
    last_error = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(url, json=payload, headers=_headers(settings))
                response.raise_for_status()
                data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as error:
            last_error = error
            if error.response.status_code not in RETRY_STATUS:
                raise
        except (httpx.TimeoutException, httpx.TransportError) as error:
            last_error = error
        if attempt < RETRY_ATTEMPTS - 1:
            await asyncio.sleep(2 ** attempt)
    raise last_error


async def chat_completion_stream(messages, settings=None):
    """流式补全：逐段 yield 正文增量。异常直接抛出，由调用方决定降级方式。"""
    settings = settings or load_settings()
    url = settings["base_url"].rstrip("/") + "/chat/completions"
    payload = _payload(messages, settings, stream=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
        async with client.stream("POST", url, json=payload, headers=_headers(settings)) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                raise RuntimeError(f"接口返回 {response.status_code}：{body[:300]}")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    if data_str == "[DONE]":
                        break
                    continue
                try:
                    chunk = json.loads(data_str)
                except ValueError:
                    continue
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield content


def _fulltext_section(item):
    """已抓取正文的条目把全文拼进 prompt；这是报告质量的关键。"""
    content = (item.get("content") or "").strip()
    if not content:
        return ""
    if len(content) > FULLTEXT_LIMIT:
        content = content[:FULLTEXT_LIMIT] + "\n…（正文过长已截断）"
    return f"- 全文（节选）：\n```\n{content}\n```\n"


async def analyze_item(item):
    prompt = PROMPT_TEMPLATE.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        category=item.get("category", ""),
        hot_value=item.get("hot_value", 0),
        hot_score=round(float(item.get("hot_score") or 0), 1),
        summary=item.get("summary", "") or "暂无摘要",
        fulltext_section=_fulltext_section(item),
    )
    return await chat_completion(
        [
            {"role": "system", "content": "你是专业的信息分析师，擅长把热点信息转化为有行动价值的洞察。"},
            {"role": "user", "content": prompt},
        ]
    )


async def analyze_item_stream(item):
    """流式版单条分析：async generator，逐段 yield markdown。"""
    prompt = PROMPT_TEMPLATE.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        category=item.get("category", ""),
        hot_value=item.get("hot_value", 0),
        hot_score=round(float(item.get("hot_score") or 0), 1),
        summary=item.get("summary", "") or "暂无摘要",
        fulltext_section=_fulltext_section(item),
    )
    async for chunk in chat_completion_stream(
        [
            {"role": "system", "content": "你是专业的信息分析师，擅长把热点信息转化为有行动价值的洞察。"},
            {"role": "user", "content": prompt},
        ]
    ):
        yield chunk


def _compact(items, per_category=5):
    from collections import defaultdict
    grouped = defaultdict(list)
    for it in items:
        grouped[it.get("category") or "未分类"].append(it)
    parts = []
    for cat, group in grouped.items():
        group.sort(
            key=lambda x: float(x.get("hot_score") or 0) if str(x.get("hot_score")).replace(".", "").isdigit() else 0,
            reverse=True,
        )
        for it in group[:per_category]:
            parts.append(
                f"- [{cat}] {it.get('title', '')} | 来源：{it.get('source', '')} | 热度分：{it.get('hot_score', 0)}"
            )
    return "\n".join(parts) if parts else "（无数据）"


async def analyze_corpus(items, category="全部", time_range="all"):
    data = _compact(items)
    prompt = CORPUS_PROMPT.format(data=data)
    return await chat_completion(
        [
            {"role": "system", "content": "你是专业的信息差分析师，擅长跨源对比、发现信息差并给出可执行建议。"},
            {"role": "user", "content": prompt},
        ]
    )


async def test_connection(settings=None):
    """用最小请求验证 API Key / 模型 / 网络连通性，返回延迟与模型名。"""
    settings = settings or load_settings()
    if not (settings.get("api_key") and settings.get("base_url") and settings.get("model")):
        raise RuntimeError("API Key / 接口地址 / 模型名称尚不完整")
    started = asyncio.get_event_loop().time()
    await chat_completion(
        [{"role": "user", "content": "回复：OK"}],
        settings={**settings, "max_tokens": 8},
    )
    latency_ms = int((asyncio.get_event_loop().time() - started) * 1000)
    return {"ok": True, "model": settings["model"], "latency_ms": latency_ms}
