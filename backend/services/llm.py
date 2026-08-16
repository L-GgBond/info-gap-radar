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
