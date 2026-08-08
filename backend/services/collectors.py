from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup


RSS_SOURCES = [
    ("BBC World", "全球新闻", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("TechCrunch", "科技", "https://techcrunch.com/feed/"),
]


async def collect_items(source: str = "all"):
    source = source.lower()
    items = []
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        if source in ("all", "github"):
            items.extend(await github_trending(client))
        if source in ("all", "hn", "hackernews"):
            items.extend(await hacker_news(client))
        if source in ("all", "rss", "news"):
            items.extend(await rss_news(client))
    return items


async def github_trending(client):
    url = "https://github.com/trending"
    response = await client.get(url, headers={"User-Agent": "InfoGapRadar/0.1"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    for repo in soup.select("article.Box-row")[:20]:
        title_node = repo.select_one("h2 a")
        if not title_node:
            continue
        title = " ".join(title_node.get_text(" ", strip=True).split())
        href = title_node.get("href", "")
        stars_node = repo.select_one("a[href$='/stargazers']")
        description_node = repo.select_one("p")
        hot_value = _parse_number(stars_node.get_text(strip=True) if stars_node else "0")
        items.append(_item(
            source="GitHub Trending",
            category="开源项目",
            title=title,
            url=f"https://github.com{href}",
            hot_value=hot_value,
            summary=description_node.get_text(" ", strip=True) if description_node else "",
        ))
    return items


async def hacker_news(client):
    response = await client.get("https://hn.algolia.com/api/v1/search?tags=front_page")
    response.raise_for_status()
    payload = response.json()
    items = []
    for hit in payload.get("hits", [])[:20]:
        title = hit.get("title") or hit.get("story_title")
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        items.append(_item(
            source="Hacker News",
            category="科技",
            title=title,
            url=link,
            hot_value=hit.get("points") or 0,
            summary=f"{hit.get('num_comments') or 0} comments on Hacker News",
        ))
    return items


async def rss_news(client):
    items = []
    for name, category, feed_url in RSS_SOURCES:
        response = await client.get(feed_url, headers={"User-Agent": "InfoGapRadar/0.1"})
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        for entry in feed.entries[:10]:
            items.append(_item(
                source=name,
                category=category,
                title=entry.get("title", ""),
                url=entry.get("link", feed_url),
                hot_value=0,
                summary=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True),
            ))
    return items


async def collect_custom_site(url: str):
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "InfoGapRadar/0.1"})
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    parsed = urlparse(url)
    candidates = []
    for anchor in soup.select("a")[:160]:
        text = anchor.get_text(" ", strip=True)
        href = anchor.get("href", "")
        if len(text) < 8 or href.startswith("#"):
            continue
        full_url = href if href.startswith("http") else f"{parsed.scheme}://{parsed.netloc}{href}"
        candidates.append(_item(
            source=parsed.netloc,
            category="自定义站点",
            title=text[:140],
            url=full_url,
            hot_value=0,
            summary="自定义站点抓取结果，第一版先提取页面可见链接，后续可为高价值站点增加专属热度规则。",
        ))
        if len(candidates) >= 25:
            break
    return candidates


def _item(source, category, title, url, hot_value, summary):
    return {
        "source": source,
        "category": category,
        "title": title,
        "url": url,
        "hot_value": int(hot_value or 0),
        "summary": summary,
        "raw_text": summary,
        "crawl_time": datetime.now(timezone.utc).isoformat(),
    }


def _parse_number(value):
    cleaned = value.replace(",", "").replace("stars", "").strip().lower()
    if cleaned.endswith("k"):
        return int(float(cleaned[:-1]) * 1000)
    try:
        return int(cleaned)
    except ValueError:
        return 0
