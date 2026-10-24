import asyncio
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from services.config import load_settings


USER_AGENT = "InfoGapRadar/0.5"
# 部分站点（尤其境内媒体）拒绝非浏览器 UA，统一用浏览器 UA 抓取
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 前沿科技 / 资讯 RSS 源，按分类归属（覆盖全部 11 个分类）
RSS_SOURCES = [
    # 境内中文源（信息差对比的"境内侧"）
    ("36氪", "创业与商业", "https://36kr.com/feed"),
    ("虎嗅", "科技", "https://www.huxiu.com/rss/0.xml"),
    ("爱范儿", "科技", "https://www.ifanr.com/feed"),
    ("极客公园", "科技", "https://www.geekpark.net/rss"),
    ("机器之心", "人工智能", "https://www.jiqizhixin.com/rss"),
    ("量子位", "人工智能", "https://www.qbitai.com/feed"),
    ("少数派", "设计与产品", "https://sspai.com/feed"),
    ("Solidot", "编程开发", "https://www.solidot.org/index.rss"),
    ("V2EX", "编程开发", "https://www.v2ex.com/index.xml"),
    ("IT之家", "科技", "https://www.ithome.com/rss/"),
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

# 境内源名单：信息差判断（insights._is_foreign）与来源展示共用
DOMESTIC_SOURCES = {
    "36氪", "虎嗅", "爱范儿", "极客公园", "机器之心", "量子位", "少数派",
    "Solidot", "V2EX", "IT之家", "知乎每日精选", "知乎热榜", "微博热搜", "InfoQ 中文",
    "百度热搜", "抖音热点", "B站热门",
}

# 每个 RSS 源最多取多少条
RSS_PER_SOURCE = 25
# Hacker News 最多取多少条
HN_LIMIT = 50
# GitHub Trending 额外抓取的语言（充实「开源项目」分类）
GITHUB_LANGS = [None, "python", "rust", "typescript", "go", "javascript",
                "java", "c++", "kotlin", "swift"]
GITHUB_PER_LANG = 15
# 并发抓取上限：60+ 个源并发拉取，总耗时受最慢几个源限制而非全部串行
FETCH_CONCURRENCY = 10
FETCH_TIMEOUT = 15

# 直连失败时走 RSSHub 公共镜像兜底的源（路由为 RSSHub 标准路径）
RSSHUB_FALLBACKS = {
    "Reddit r/programming": "/reddit/r/programming",
    "Reddit r/rust": "/reddit/r/rust",
    "Reddit r/python": "/reddit/r/python",
    "虎嗅": "/huxiu/article",
    "微博热搜": "/weibo/search/hot",
}

RANGE_DAYS = {"week": 7, "month": 30, "quarter": 90, "year": 365}


def available_sources(extra_feeds=None):
    """返回所有可采集数据源（用于前端做开关）。extra_feeds 为用户自定义 RSS。"""
    out = []
    for name, category, _url in RSS_SOURCES:
        out.append({"id": name, "name": name, "category": category, "custom": False})
    for feed in extra_feeds or []:
        out.append({
            "id": f"feed:{feed['id']}",
            "name": feed["name"] or feed["url"],
            "category": feed.get("category") or "科技",
            "custom": True,
        })
    out.append({"id": "github", "name": "GitHub Trending（多语言）", "category": "开源项目", "custom": False})
    out.append({"id": "hackernews", "name": "Hacker News", "category": "科技", "custom": False})
    out.append({"id": "weibo", "name": "微博热搜", "category": "全球新闻", "custom": False})
    out.append({"id": "zhihu", "name": "知乎热榜", "category": "科技", "custom": False})
    out.append({"id": "baidu", "name": "百度热搜", "category": "全球新闻", "custom": False})
    out.append({"id": "douyin", "name": "抖音热点", "category": "全球新闻", "custom": False})
    out.append({"id": "bilibili", "name": "B站热门", "category": "科技", "custom": False})
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


# ===== 热度归一化 =====

def normalize_hot_scores(items):
    """跨源热度归一化：按来源内百分位映射到 0~100。

    GitHub 的总 star、HN 的 points、RSS 的位次口径完全不同，直接比较没有意义；
    归一化后所有来源都在同一把 0~100 的尺子上，列表排序才成立。
    全部热度相同的源（如 RSS 恒为位次 0）改用条目新旧排名。
    """
    by_source = {}
    for it in items:
        by_source.setdefault(it.get("source") or "未知", []).append(it)

    scores = {}
    for source, group in by_source.items():
        hots = [_hot(it) for it in group]
        if len(set(hots)) > 1:
            ranked = sorted(hots)
            n = len(ranked)
            for it, h in zip(group, hots):
                below = sum(1 for v in ranked if v < h)
                scores[id(it)] = round(100.0 * below / max(n - 1, 1), 1)
        else:
            # 同源同热度：按时间新→旧给 100→0 的位次分
            ordered = sorted(
                group,
                key=lambda x: x.get("item_date") or "",
                reverse=True,
            )
            n = len(ordered)
            for idx, it in enumerate(ordered):
                scores[id(it)] = round(100.0 * (n - 1 - idx) / max(n - 1, 1), 1)

    for it in items:
        it["hot_score"] = scores.get(id(it), 0.0)
    return items


def _hot(item):
    try:
        return int(item.get("hot_value") or 0)
    except (TypeError, ValueError):
        return 0


# ===== 并发采集入口 =====

async def collect_items(source="all", time_range="all", enabled_sources=None,
                        category=None, extra_feeds=None):
    """并发采集全部启用源。返回 (items, statuses)。

    statuses 为每源采集结果：{source, category, ok, count, error}，用于前端反馈。
    """
    source = (source or "all").lower()
    category = category or "全部"
    cutoff_dt, cutoff_ts = range_cutoff(time_range)
    statuses = []

    want_github = (
        source in ("all", "github")
        and (enabled_sources is None or "github" in enabled_sources)
        and category in ("全部", "开源项目")
    )
    want_hn = (
        source in ("all", "hn", "hackernews")
        and (enabled_sources is None or "hackernews" in enabled_sources)
        and category in ("全部", "科技")
    )
    want_weibo = (
        source in ("all", "weibo")
        and (enabled_sources is None or "weibo" in enabled_sources)
        and category in ("全部", "全球新闻")
    )
    want_zhihu = (
        source in ("all", "zhihu")
        and (enabled_sources is None or "zhihu" in enabled_sources)
        and category in ("全部", "科技")
    )
    want_baidu = (
        source in ("all", "baidu")
        and (enabled_sources is None or "baidu" in enabled_sources)
        and category in ("全部", "全球新闻")
    )
    want_douyin = (
        source in ("all", "douyin")
        and (enabled_sources is None or "douyin" in enabled_sources)
        and category in ("全部", "全球新闻")
    )
    want_bilibili = (
        source in ("all", "bilibili")
        and (enabled_sources is None or "bilibili" in enabled_sources)
        and category in ("全部", "科技")
    )
    want_rss = source in ("all", "rss", "news")
    rss_category = category if category != "全部" else None

    # 组装 RSS 任务清单（内置源按开关/分类过滤；自定义源始终参与）
    feed_tasks = []
    if want_rss:
        for name, cat, feed_url in RSS_SOURCES:
            if enabled_sources is not None and name not in enabled_sources:
                continue
            if rss_category is not None and cat != rss_category:
                continue
            feed_tasks.append((name, cat, feed_url))
        for feed in extra_feeds or []:
            feed_tasks.append((feed["name"], feed.get("category") or "科技", feed["url"]))

    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def guarded(name, cat, coro_factory):
        """单源采集：失败自动重试 1 次，状态始终上报。"""
        async with semaphore:
            started = time.monotonic()
            last_error = None
            for attempt in range(2):
                try:
                    items = await coro_factory()
                    statuses.append({
                        "source": name, "category": cat, "ok": True,
                        "count": len(items), "error": None,
                        "ms": int((time.monotonic() - started) * 1000),
                    })
                    return items
                except Exception as error:  # noqa: BLE001 - 单源失败不影响整体
                    last_error = error
                    if attempt == 0:
                        await asyncio.sleep(1)
            statuses.append({
                "source": name, "category": cat, "ok": False,
                "count": 0, "error": str(last_error)[:200],
                "ms": int((time.monotonic() - started) * 1000),
            })
            return []

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT, follow_redirects=True,
        headers={"User-Agent": BROWSER_UA},
    ) as client:
        tasks = []
        if want_github:
            tasks.append(guarded("GitHub Trending", "开源项目",
                                 lambda: github_trending(client, github_since(time_range))))
        if want_hn:
            tasks.append(guarded("Hacker News", "科技",
                                 lambda: hacker_news(client, cutoff_ts)))
        if want_weibo:
            tasks.append(guarded("微博热搜", "全球新闻",
                                 lambda: weibo_hot_search(client)))
        if want_zhihu:
            tasks.append(guarded("知乎热榜", "科技",
                                 lambda: zhihu_hot_search(client)))
        if want_baidu:
            tasks.append(guarded("百度热搜", "全球新闻",
                                 lambda: baidu_hot_search(client)))
        if want_douyin:
            tasks.append(guarded("抖音热点", "全球新闻",
                                 lambda: douyin_hot_search(client)))
        if want_bilibili:
            tasks.append(guarded("B站热门", "科技",
                                 lambda: bilibili_popular(client)))
        for name, cat, feed_url in feed_tasks:
            tasks.append(guarded(name, cat,
                                 lambda u=feed_url, c=cat, n=name: rss_feed(client, u, c, n, cutoff_dt)))
        results = await asyncio.gather(*tasks)

    items = [it for group in results for it in group]

    # 跨源去重（自定义站点与 RSS 可能引用同一 URL）
    seen = set()
    unique = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        unique.append(it)

    normalize_hot_scores(unique)
    return unique, statuses


# ===== 各源采集器 =====

_STARS_TODAY_RE = re.compile(r"([\d,\.]+)\s*stars?\s*(today|this week|this month)", re.I)
_PERIOD_DAYS = {"today": 1, "this week": 7, "this month": 30}


def _github_heat(repo):
    """从 trending 卡片解析"今日/本周/本月 star 增量"，折算为日增量；解析失败回退总 star。"""
    text = ""
    for span in repo.select("span"):
        s = span.get_text(" ", strip=True)
        if "stars" in s and ("today" in s or "week" in s or "month" in s):
            text = s
            break
    if text:
        m = _STARS_TODAY_RE.search(text)
        if m:
            value = float(m.group(1).replace(",", ""))
            days = _PERIOD_DAYS.get(m.group(2).lower(), 1)
            return max(1, round(value / days))
    stars_node = repo.select_one("a[href$='/stargazers']")
    return _parse_number(stars_node.get_text(strip=True) if stars_node else "0")


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
            description_node = repo.select_one("p")
            stars_node = repo.select_one("a[href$='/stargazers']")
            total_stars = _parse_number(stars_node.get_text(strip=True) if stars_node else "0")
            items.append(_item(
                source="GitHub Trending",
                category="开源项目",
                title=f"{title}",
                url=full,
                hot_value=_github_heat(repo),
                summary=(description_node.get_text(" ", strip=True) if description_node else "")
                        + (f"（总星数 {total_stars}）" if total_stars else ""),
                item_date=now,
            ))
    return items


async def hacker_news(client, cutoff_ts=None):
    if cutoff_ts:
        # 时间范围查询：限定 points>20，取范围内真正有热度的讨论
        url = (
            f"https://hn.algolia.com/api/v1/search?tags=(story,poll)"
            f"&numericFilters=created_at_i%3E{cutoff_ts},points%3E20&hitsPerPage={HN_LIMIT}"
        )
    else:
        url = f"https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={HN_LIMIT}"
    response = await client.get(url)
    response.raise_for_status()
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


async def weibo_hot_search(client):
    """微博热搜（公开 JSON 接口）。失败时静默跳过。"""
    response = await client.get("https://weibo.com/ajax/side/hotSearch")
    response.raise_for_status()
    payload = response.json()
    items = []
    for entry in (payload.get("data") or {}).get("realtime") or []:
        word = entry.get("word")
        if not word:
            continue
        items.append(_item(
            source="微博热搜",
            category="全球新闻",
            title=word,
            url=f"https://s.weibo.com/weibo?q=%23{quote_plus(word)}%23",
            hot_value=int(entry.get("raw_hot") or 0),
            summary=f"微博热搜第 {entry.get('rank') or '?'} 位",
        ))
    return items[:30]


async def zhihu_hot_search(client):
    """知乎热榜（api.zhihu.com 公开 JSON 接口）。"""
    response = await client.get("https://api.zhihu.com/topstory/hot-list?limit=20")
    response.raise_for_status()
    payload = response.json()

    def _web_url(target):
        raw = target.get("url") or ""
        for prefix, web in (("questions/", "question/"), ("pins/", "pin/"), ("articles/", "p/")):
            if prefix in raw:
                tail = raw.split(prefix)[-1].split("/")[0].split("?")[0]
                return f"https://www.zhihu.com/{web}{tail}"
        return raw or "https://www.zhihu.com/hot"

    items = []
    for entry in payload.get("data") or []:
        target = entry.get("target") or {}
        title = target.get("title")
        if not title:
            continue
        # detail_text 形如 "1234 万热度"
        heat = 0
        digits = re.findall(r"[\d.]+", entry.get("detail_text") or "")
        if digits:
            try:
                value = float(digits[0])
                heat = int(value * 10000 if "万" in (entry.get("detail_text") or "") else value)
            except ValueError:
                heat = 0
        items.append(_item(
            source="知乎热榜",
            category="科技",
            title=title,
            url=_web_url(target),
            hot_value=heat,
            summary=(target.get("excerpt") or "").strip()[:300],
        ))
    return items[:20]


async def baidu_hot_search(client):
    """百度实时热搜（top.baidu.com 公开 JSON 接口）。"""
    response = await client.get(
        "https://top.baidu.com/api/board?platform=wise&tab=realtime",
        headers={"Referer": "https://top.baidu.com/board?tab=realtime"},
    )
    response.raise_for_status()
    payload = response.json()
    items = []
    for card in (payload.get("data") or {}).get("cards") or []:
        # 接口存在两层 content 嵌套：cards[].content[] 里再套 content[]
        groups = card.get("content") or []
        for group in groups:
            inner = group.get("content") if isinstance(group, dict) and "content" in group else [group]
            for entry in inner or []:
                word = entry.get("word")
                if not word:
                    continue
                try:
                    hot = int(float(entry.get("hotScore") or 0))
                except (TypeError, ValueError):
                    hot = 0
                items.append(_item(
                    source="百度热搜",
                    category="全球新闻",
                    title=word,
                    url=entry.get("url") or f"https://www.baidu.com/s?wd={quote_plus(word)}",
                    hot_value=hot,
                    summary=(entry.get("desc") or "").strip()[:300],
                ))
    return items[:30]


async def douyin_hot_search(client):
    """抖音热点榜（公开 JSON 接口，结构多变做防御式解析）。"""
    response = await client.get(
        "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/",
        headers={"Referer": "https://www.douyin.com/"},
    )
    response.raise_for_status()
    payload = response.json()
    words = (
        ((payload.get("data") or {}).get("word_list"))
        or payload.get("word_list")
        or payload.get("data")
        or []
    )
    items = []
    for entry in words:
        if not isinstance(entry, dict):
            continue
        word = entry.get("word") or entry.get("title")
        if not word:
            continue
        hot = entry.get("hot_value") or entry.get("view_count") or 0
        items.append(_item(
            source="抖音热点",
            category="全球新闻",
            title=str(word),
            url=f"https://www.douyin.com/search/{quote_plus(str(word))}",
            hot_value=int(hot) if str(hot).isdigit() else 0,
            summary="抖音热点榜条目",
        ))
    return items[:30]


async def bilibili_popular(client):
    """B站热门视频榜（公开 JSON 接口）。"""
    response = await client.get(
        "https://api.bilibili.com/x/web-interface/popular",
        headers={"Referer": "https://www.bilibili.com/"},
    )
    response.raise_for_status()
    payload = response.json()
    videos = ((payload.get("data") or {}).get("list")) or []
    items = []
    for video in videos[:30]:
        title = video.get("title")
        if not title:
            continue
        stat = video.get("stat") or {}
        url = video.get("short_link_v2") or (
            f"https://www.bilibili.com/video/{video.get('bvid')}" if video.get("bvid") else ""
        )
        if not url:
            continue
        items.append(_item(
            source="B站热门",
            category="科技",
            title=str(title),
            url=url,
            hot_value=int(stat.get("view") or 0),
            summary=f"UP主 {video.get('owner', {}).get('name', '未知')} · 播放 {stat.get('view', 0)}",
        ))
    return items


async def _fetch_feed_text(client, name, feed_url):
    """抓取 feed 原文；配置了 RSSHub 镜像且该源有兜底路由时，失败自动切镜像。"""
    try:
        response = await client.get(feed_url)
        response.raise_for_status()
        return response.text
    except Exception:
        route = RSSHUB_FALLBACKS.get(name)
        if not route:
            raise
        mirror = (load_settings().get("rsshub_mirror") or "").rstrip("/")
        if not mirror:
            raise
        response = await client.get(mirror + route)
        response.raise_for_status()
        return response.text


def _entry_text(entry):
    """优先取 content:encoded 完整正文，回退 summary；剥离 HTML 标签。"""
    raw = ""
    content = entry.get("content")
    if isinstance(content, list) and content:
        raw = content[0].get("value") or ""
    if not raw:
        raw = entry.get("summary") or entry.get("description") or ""
    return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)[:1500]


async def rss_feed(client, feed_url, category, source_name, cutoff_dt=None):
    """抓取单个 RSS 源。位次作为初始热度（榜单靠前更热），再由归一化统一口径。"""
    def parse(text):
        feed = feedparser.parse(text)
        items = []
        now = datetime.now(timezone.utc)
        for idx, entry in enumerate(feed.entries[:RSS_PER_SOURCE]):
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                dt = datetime(*published[:6], tzinfo=timezone.utc)
            else:
                dt = now
            if cutoff_dt and dt < cutoff_dt:
                continue
            items.append(_item(
                source=source_name,
                category=category,
                title=entry.get("title", ""),
                url=entry.get("link", feed_url),
                hot_value=(RSS_PER_SOURCE - idx) * 5,
                summary=_entry_text(entry),
                item_date=dt.isoformat(),
            ))
        return items

    items = parse(await _fetch_feed_text(client, source_name, feed_url))
    if not items and source_name in RSSHUB_FALLBACKS:
        # 直连 200 但不是有效 feed（WAF 挑战页/空响应）：配置了镜像则再试一次
        mirror = (load_settings().get("rsshub_mirror") or "").rstrip("/")
        if mirror and not feed_url.startswith(mirror):
            try:
                response = await client.get(mirror + RSSHUB_FALLBACKS[source_name])
                response.raise_for_status()
                items = parse(response.text)
            except Exception:  # noqa: BLE001 - 镜像也失败则维持空结果
                pass
    return items


# ===== 自定义站点 =====

_NAV_NOISE = re.compile(
    r"^(首页|更多|登录|注册|下一页|上一页|返回|搜索|评论|详情|全部|read more|more|next|previous|home|login|sign ?up|search|all|back|share|subscribe|menu|skip to.*|advertisement.*)$",
    re.I,
)


def _clean_link_text(text):
    text = (text or "").strip()
    if len(text) < 8 or len(text) > 140:
        return None
    if _NAV_NOISE.match(text):
        return None
    return text


def _clean_link_href(href, base_url):
    href = (href or "").strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    return urljoin(base_url, href.split("#")[0])


async def collect_custom_site(url):
    """抓取自定义站点：提取正文区可见链接，过滤导航噪音，按 URL 去重。"""
    async with httpx.AsyncClient(
        timeout=12, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    parsed = urlparse(url)
    page_title = soup.title.get_text(" ", strip=True) if soup.title else parsed.netloc
    candidates = []
    seen = set()
    now = datetime.now(timezone.utc).isoformat()
    for anchor in soup.select("a")[:200]:
        if anchor.find_parent(["nav", "header", "footer"]):
            continue
        text = _clean_link_text(anchor.get_text(" ", strip=True))
        full_url = _clean_link_href(anchor.get("href", ""), url)
        if not text or not full_url or full_url in seen:
            continue
        seen.add(full_url)
        candidates.append(_item(
            source=parsed.netloc,
            category="自定义站点",
            title=text,
            url=full_url,
            hot_value=0,
            summary=f"来自自定义站点「{page_title}」的链接。",
            item_date=now,
        ))
        if len(candidates) >= 50:
            break
    return candidates, page_title


# ===== OPML 导入 / 导出 =====

def parse_opml(text):
    """解析 OPML 订阅列表，返回 [{name, url, category}]。

    分类取父级目录 outline 的 text；顶层条目归入「科技」。坏条目跳过。
    """
    root = ET.fromstring(text)
    feeds = []

    def walk(node, folder):
        for child in node.findall("outline"):
            xml_url = child.get("xmlUrl")
            if xml_url:
                name = child.get("title") or child.get("text") or urlparse(xml_url).netloc
                feeds.append({
                    "name": name.strip(),
                    "url": xml_url.strip(),
                    "category": folder or "科技",
                })
            else:
                walk(child, folder or child.get("text"))

    # OPML 的 outline 都在 <body> 下；直接从 body 开始按目录层级遍历
    body = root.find("body")
    walk(body if body is not None else root, None)
    return feeds


def export_opml(feeds, title="信息差雷达订阅"):
    """把订阅源列表导出为 OPML 2.0 XML 字符串。"""
    body = []
    for feed in feeds:
        name = (feed.get("name") or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
        url = (feed.get("url") or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
        body.append(f'    <outline type="rss" text="{name}" title="{name}" xmlUrl="{url}"/>')
    groups = {}
    for feed in feeds:
        groups.setdefault(feed.get("category") or "未分类", []).append(feed)
    def render_group(cat, group):
        safe_cat = cat.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
        lines = [f'    <outline text="{safe_cat}" title="{safe_cat}">']
        for feed in group:
            name = (feed.get("name") or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
            url = (feed.get("url") or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
            lines.append(f'      <outline type="rss" text="{name}" title="{name}" xmlUrl="{url}"/>')
        lines.append("    </outline>")
        return lines
    inner = []
    for cat, group in groups.items():
        inner.extend(render_group(cat, group))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<opml version="2.0">\n'
        "  <head>\n"
        f"    <title>{title}</title>\n"
        "  </head>\n"
        "  <body>\n"
        + "\n".join(inner) + "\n"
        "  </body>\n"
        "</opml>\n"
    )


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
        "hot_score": 0.0,
    }


def _parse_number(value):
    cleaned = value.replace(",", "").replace("stars", "").strip().lower()
    if cleaned.endswith("k"):
        return int(float(cleaned[:-1]) * 1000)
    try:
        return int(cleaned)
    except ValueError:
        return 0
