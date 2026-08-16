import httpx

from services.config import load_settings

PROMPT_TEMPLATE = """你是信息差分析师，基于下面的热点条目信息，生成一份简洁的中文分析报告。

条目信息：
- 标题：{title}
- 来源：{source}
- 分类：{category}
- 热度值：{hot_value}
- 摘要：{summary}

报告需要包含下面模块（使用 markdown 格式，直接输出正文，不要废话）：
1. ## 核心简述：这件事/这个项目到底是什么
2. ## 热点原因：为什么它现在热度高（如信息不足，可基于领域常识合理推断并注明）
3. ## 价值信息：可以学到什么、有什么用处、适合谁
4. ## 潜在风险：可能的缺点、坑或风险
5. ## 延伸洞察：普通人可以获得什么信息差、可以采取的行动

输出 markdown 格式。"""


def llm_configured():
    settings = load_settings()
    return bool(settings.get("api_key") and settings.get("base_url") and settings.get("model"))


async def chat_completion(messages, settings=None):
    settings = settings or load_settings()
    url = settings["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": settings["model"],
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 1200,
    }
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings['api_key']}"},
        )
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]["content"]


async def analyze_item(item):
    prompt = PROMPT_TEMPLATE.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        category=item.get("category", ""),
        hot_value=item.get("hot_value", 0),
        summary=item.get("summary", "") or "暂无摘要",
    )
    return await chat_completion(
        [
            {"role": "system", "content": "你是专业的信息分析师，擅长把热点信息转化为有行动价值的洞察。"},
            {"role": "user", "content": prompt},
        ]
    )


CORPUS_PROMPT = """你是信息差分析师。下面是一批已采集的热点条目（按分类聚合，仅保留每条的标题、来源、分类与热度）。
请基于这些信息，生成一份中文「信息差洞察」报告，目标是帮助读者发现：哪些话题在境外/技术圈已经很热、但在中文普通读者中尚未充分覆盖（即信息差），以及值得普通人关注和行动的信号。

条目数据：
{data}

请输出 markdown 格式，包含以下模块（直接输出正文，不要废话）：
1. ## 总体态势：这批热点反映的大趋势
2. ## 信息差机会：境外/技术圈已热、中文世界尚冷的具体话题（给出 3-6 条，每条点名条目并说明为什么是信息差）
3. ## 值得跟进的信号：最可能持续发酵或影响普通人的方向
4. ## 行动建议：普通人可以怎么利用这些信息差（学习、投资、副业、避坑等）

输出 markdown 格式。"""


def _compact(items, per_category=4):
    from collections import defaultdict
    grouped = defaultdict(list)
    for it in items:
        grouped[it.get("category") or "未分类"].append(it)
    parts = []
    for cat, group in grouped.items():
        group.sort(
            key=lambda x: int(x.get("hot_value") or 0) if str(x.get("hot_value")).isdigit() else 0,
            reverse=True,
        )
        for it in group[:per_category]:
            parts.append(
                f"- [{cat}] {it.get('title', '')} | 来源：{it.get('source', '')} | 热度：{it.get('hot_value', 0)}"
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
