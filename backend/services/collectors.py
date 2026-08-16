from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup


USER_AGENT = "InfoGapRadar/0.2"

# 前沿科技 / 资讯 RSS 源，按分类归属
RSS_SOURCES = [
    ("arXiv AI", "人工智能", "https://export.arxiv.org/rss/cs.AI"),
    ("MIT Technology Review", "人工智能", "https://www.technologyreview.com/feed/"),
    ("TechCrunch", "科技", "https://techcrunch.com/feed/"),
    ("The Verge", "科技", "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica", "科技", "https://feeds.arstechnica.com/arstechnica/index"),
    ("Wired", "科技", "https://www.wired.com/feed/rss"),
    ("BBC World", "全球新闻", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("The Guardian World", "全球新闻", "https://www.theguardian.com/world/rss"),
    ("Product Hunt", "创业与商业", "https://www.producthunt.com/feed"),
    ("Reddit r/programming", "编程开发", "https://www.reddit.com/r/programming/.rss"),
    ("InfoQ 中文", "编程开发", "https://www.infoq.cn/feed"),
    ("CoinDesk", "区块链与加密货币", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("BleepingComputer", "网络安全", "https://www.bleepingcomputer.com/feed/"),
    ("ScienceDaily", "科学", "https://www.sciencedaily.com/rss/all.xml"),
    ("Smashing Magazine", "设计与产品", "https://www.smashingmagazine.com/feed/"),
]

RANGE_DAYS = {"week": 7, "month": 30, "quarter": 90, "year": 365}


def range_cutoff(time_range: str):
    """按时间范围计算截止时间，返回 (cutoff_dt, cutoff_ts)。"""
    days = RANGE_DAYS.get((time_range or "all").lower())
    if not days:
        return None, None
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff_dt, int(cutoff_dt.timestamp())


def github_since(time_range: str):
    return {
        "week": "weekly",
        "month": "monthly",
        "quarter": "monthly",
        "year": "monthly",
    }.get((time_range or "").lower(), "daily")


async def collect_items(source: str = "all", time_range: str = "all"):
    source = (source or "all").lower()
    cutoff_dt, cutoff_ts = range_cutoff(time_range)
    items = []
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        if source in ("all", "github"):
            items.extend(await github_trending(client, github_since(time_range)))
        if source in ("all", "hn", "hackernews"):
            items.extend(await hacker_news(client, cutoff_ts))
        if source in ("all", "rss", "news"):
            items.extend(await rss_news(client, cutoff_dt))
    return items


async def github_trending(client, since="daily"):
    url = "https://github.com/trending" + (
        f"?since={since}" if since and since != "daily" else ""
    )
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    now = datetime.now(timezone.utc).isoformat()
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
            item_date=now,
        ))
    return items


async def hacker_news(client, cutoff_ts=None):
    if cutoff_ts:
        url = (
            f"https://hn.algolia.com/api/v1/search?tags=(story,poll)"
            f"&numericFilters=created_at_i%3E{cutoff_ts}&hitsPerPage=30"
        )
    else:
        url = "https://hn.algolia.com/api/v1/search?tags=front_page"
    response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    items = []
    for hit in payload.get("hits", [])[:20]:
        title = hit.get("title") or hit.get("story_title")
        if not title:
            continue
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        items.append(_item(
            source="Hacker News",
            category="科技",
            title=title,
            url=link,
            hot_value=hit.get("points") or 0,
            summary=f"{hit.get('num_comments') or 0} comments on Hacker News",
            item_date=hit.get("created_at") or "",
        ))
    return items


async def rss_news(client, cutoff_dt=None):
    items = []
    now = datetime.now(timezone.utc)
    for name, category, feed_url in RSS_SOURCES:
        try:
            response = await client.get(feed_url)
            response.raise_for_status()
            feed = feedparser.parse(response.text)
        except Exception:
            continue
        for entry in feed.entries[:8]:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                dt = datetime(*published[:6], tzinfo=timezone.utc)
            else:
                dt = now
            if cutoff_dt and dt < cutoff_dt:
                continue
            items.append(_item(
                source=name,
                category=category,
                title=entry.get("title", ""),
                url=entry.get("link", feed_url),
                hot_value=0,
                summary=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True),
                item_date=dt.isoformat(),
            ))
    return items


async def collect_custom_site(url: str):
    async with httpx.AsyncClient(
        timeout=12, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    parsed = urlparse(url)
    candidates = []
    now = datetime.now(timezone.utc).isoformat()
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
            item_date=now,
        ))
        if len(candidates) >= 25:
            break
    return candidates


def _item(source, category, title, url, hot_value, summary, item_date=None):
    return {
        "source": source,
        "category": category,
        "title": title,
        "url": url,
        "hot_value": int(hot_value or 0),
        "summary": summary,
        "raw_text": summary,
        "item_date": item_date or datetime.now(timezone.utc).isoformat(),
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
