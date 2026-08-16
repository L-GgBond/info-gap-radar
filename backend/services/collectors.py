from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup


USER_AGENT = "InfoGapRadar/0.3"

# 前沿科技 / 资讯 RSS 源，按分类归属（扩展版，覆盖全部 11 个分类）
RSS_SOURCES = [
    # 人工智能
    ("arXiv AI", "人工智能", "https://export.arxiv.org/rss/cs.AI"),
    ("arXiv 机器学习", "人工智能", "https://export.arxiv.org/rss/cs.LG"),
    ("arXiv NLP", "人工智能", "https://export.arxiv.org/rss/cs.CL"),
    ("MIT Technology Review", "人工智能", "https://www.technologyreview.com/feed/"),
    ("Hugging Face Blog", "人工智能", "https://huggingface.co/blog/feed.xml"),
    ("The Batch", "人工智能", "https://www.deeplearning.ai/the-batch/feed/"),
    # 编程开发
    ("Reddit r/programming", "编程开发", "https://www.reddit.com/r/programming/.rss"),
    ("Reddit r/rust", "编程开发", "https://www.reddit.com/r/rust/.rss"),
    ("Reddit r/python", "编程开发", "https://www.reddit.com/r/python/.rss"),
    ("InfoQ 中文", "编程开发", "https://www.infoq.cn/feed"),
    ("Dev.to", "编程开发", "https://dev.to/feed"),
    ("Lobsters", "编程开发", "https://lobste.rs/rss"),
    # 开源项目（主源为 GitHub Trending，见 github_trending 多语言抓取）
    ("GitLab Blog", "开源项目", "https://about.gitlab.com/atom.xml"),
    ("CNCF Blog", "开源项目", "https://www.cncf.io/feed/"),
    # 科技
    ("TechCrunch", "科技", "https://techcrunch.com/feed/"),
    ("The Verge", "科技", "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica", "科技", "https://feeds.arstechnica.com/arstechnica/index"),
    ("Wired", "科技", "https://www.wired.com/feed/rss"),
    ("Engadget", "科技", "https://www.engadget.com/rss.xml"),
    ("IEEE Spectrum", "科技", "https://spectrum.ieee.org/feeds/topic/technology.rss"),
    # 全球新闻
    ("BBC World", "全球新闻", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("The Guardian World", "全球新闻", "https://www.theguardian.com/world/rss"),
    ("Al Jazeera", "全球新闻", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("NPR News", "全球新闻", "https://feeds.npr.org/1004/rss.xml"),
    # 创业与商业
    ("Product Hunt", "创业与商业", "https://www.producthunt.com/feed"),
    ("Bloomberg Tech", "创业与商业", "https://feeds.bloomberg.com/technology/news.rss"),
    ("Forbes Innovation", "创业与商业", "https://www.forbes.com/innovation/feed/"),
    ("TechCrunch Startups", "创业与商业", "https://techcrunch.com/category/startups/feed/"),
    # 设计与产品
    ("Smashing Magazine", "设计与产品", "https://www.smashingmagazine.com/feed/"),
    ("Nielsen Norman Group", "设计与产品", "https://www.nngroup.com/feed/rss/"),
    ("A List Apart", "设计与产品", "https://alistapart.com/main/feed/"),
    ("Designer News", "设计与产品", "https://www.designernews.co/?format=rss"),
    # 区块链与加密货币
    ("CoinDesk", "区块链与加密货币", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "区块链与加密货币", "https://cointelegraph.com/rss"),
    ("Bitcoin Magazine", "区块链与加密货币", "https://bitcoinmagazine.com/.rss/full/"),
    ("The Block", "区块链与加密货币", "https://www.theblock.co/rss.xml"),
    # 网络安全
    ("BleepingComputer", "网络安全", "https://www.bleepingcomputer.com/feed/"),
    ("Krebs on Security", "网络安全", "https://krebsonsecurity.com/feed/"),
    ("The Hacker News", "网络安全", "https://feeds.feedburner.com/TheHackersNews"),
    ("Dark Reading", "网络安全", "https://www.darkreading.com/rss.xml"),
    # 科学
    ("ScienceDaily", "科学", "https://www.sciencedaily.com/rss/all.xml"),
    ("Nature", "科学", "https://www.nature.com/nature.rss"),
    ("Scientific American", "科学", "https://www.scientificamerican.com/feed/"),
    ("Phys.org", "科学", "https://phys.org/rss-feed/"),
    ("EurekAlert", "科学", "https://www.eurekalert.org/rss.xml"),
]

# 每个 RSS 源最多取多少条
RSS_PER_SOURCE = 12
# Hacker News 最多取多少条
HN_LIMIT = 30
# GitHub Trending 额外抓取的语言（充实「开源项目」分类）
GITHUB_LANGS = [None, "python", "rust", "typescript", "go", "javascript"]
GITHUB_PER_LANG = 10

RANGE_DAYS = {"week": 7, "month": 30, "quarter": 90, "year": 365}


def available_sources():
    """返回所有可采集数据源（用于前端做开关）。RSS 以源名为 id，GitHub/Hacker News 为独立项。"""
    out = []
    for name, category, _url in RSS_SOURCES:
        out.append({"id": name, "name": name, "category": category})
    out.append({"id": "github", "name": "GitHub Trending（多语言）", "category": "开源项目"})
    out.append({"id": "hackernews", "name": "Hacker News", "category": "科技"})
    return out


def default_enabled_sources():
    """默认全部开启。"""
    return [s["id"] for s in available_sources()]


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


async def collect_items(source: str = "all", time_range: str = "all", enabled_sources=None, category: str = None):
    source = (source or "all").lower()
    cutoff_dt, cutoff_ts = range_cutoff(time_range)
    items = []
    category = category or "全部"
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        if (
            source in ("all", "github")
            and (enabled_sources is None or "github" in enabled_sources)
            and category in ("全部", "开源项目")
        ):
            items.extend(await github_trending(client, github_since(time_range)))
        if (
            source in ("all", "hn", "hackernews")
            and (enabled_sources is None or "hackernews" in enabled_sources)
            and category in ("全部", "科技")
        ):
            items.extend(await hacker_news(client, cutoff_ts))
        if source in ("all", "rss", "news"):
            rss_category = category if category != "全部" else None
            items.extend(await rss_news(client, cutoff_dt, enabled_sources, rss_category))
    return items


async def github_trending(client, since="daily"):
    items = []
    seen = set()
    for lang in GITHUB_LANGS:
        path = "https://github.com/trending" + (f"/{lang}" if lang else "")
        if since and since != "daily":
            path += f"?since={since}"
        try:
            response = await client.get(path)
            response.raise_for_status()
        except Exception:
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        now = datetime.now(timezone.utc).isoformat()
        for repo in soup.select("article.Box-row")[:GITHUB_PER_LANG]:
            title_node = repo.select_one("h2 a")
            if not title_node:
                continue
            title = " ".join(title_node.get_text(" ", strip=True).split())
            href = title_node.get("href", "")
            full = f"https://github.com{href}"
            if full in seen:
                continue
            seen.add(full)
            stars_node = repo.select_one("a[href$='/stargazers']")
            description_node = repo.select_one("p")
            hot_value = _parse_number(stars_node.get_text(strip=True) if stars_node else "0")
            lang_label = f"[{lang}] " if lang else ""
            items.append(_item(
                source="GitHub Trending",
                category="开源项目",
                title=f"{lang_label}{title}",
                url=full,
                hot_value=hot_value,
                summary=description_node.get_text(" ", strip=True) if description_node else "",
                item_date=now,
            ))
    return items


async def hacker_news(client, cutoff_ts=None):
    if cutoff_ts:
        url = (
            f"https://hn.algolia.com/api/v1/search?tags=(story,poll)"
            f"&numericFilters=created_at_i%3E{cutoff_ts}&hitsPerPage={HN_LIMIT}"
        )
    else:
        url = f"https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={HN_LIMIT}"
    try:
        response = await client.get(url)
        response.raise_for_status()
    except Exception:
        return []
    payload = response.json()
    items = []
    for hit in payload.get("hits", [])[:HN_LIMIT]:
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


async def rss_news(client, cutoff_dt=None, enabled_sources=None, category=None):
    items = []
    now = datetime.now(timezone.utc)
    for name, cat, feed_url in RSS_SOURCES:
        if enabled_sources is not None and name not in enabled_sources:
            continue
        if category is not None and cat != category:
            continue
        item_category = category if category is not None else cat
        try:
            response = await client.get(feed_url)
            response.raise_for_status()
            feed = feedparser.parse(response.text)
        except Exception:
            continue
        for entry in feed.entries[:RSS_PER_SOURCE]:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                dt = datetime(*published[:6], tzinfo=timezone.utc)
            else:
                dt = now
            if cutoff_dt and dt < cutoff_dt:
                continue
            items.append(_item(
                source=name,
                category=item_category,
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
        try:
            response = await client.get(url)
            response.raise_for_status()
        except Exception:
            return []
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
        if len(candidates) >= 50:
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
