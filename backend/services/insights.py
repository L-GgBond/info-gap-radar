import math
import re

from services.collectors import DOMESTIC_SOURCES


def build_report(item):
    title = item.get("title", "")
    source = item.get("source", "")
    category = item.get("category", "")
    summary = item.get("summary", "") or "暂无摘要。"
    hot_value = item.get("hot_value", 0)

    return f"""# {title}

## 核心简述
这条信息来自 **{source}**，属于 **{category}** 分类。当前热度值为 **{hot_value}**，可作为初步筛选信号。

## 热点原因
- 标题具备被转发或讨论的潜力。
- 来源本身具有较高的信息密度。
- 如果该条目持续出现在榜单或多源重复出现，说明它可能正在形成趋势。

## 价值信息
{summary}

## 潜在风险
- 第一版报告使用本地规则生成，还没有接入真实大模型 API。
- 热度值来自不同平台，口径不完全一致，不能直接横向比较。
- 新闻与网页内容需要保留来源链接，避免完整转载带来的版权风险。

## 延伸洞察
可以把这条信息加入关注列表，继续监控它是否在 GitHub、HN、RSS 新闻源等多个渠道重复出现。多源共振通常比单点爆火更有商业和学习价值。
"""


DOMESTIC_HINTS = [
    "中文", "中国", "网易", "知乎", "微博", "36氪", "少数派", "掘金", "开源中国",
    "机器之心", "量子位", "虎嗅", "钛媒体", "澎湃", "界面", "新浪", "腾讯", "阿里",
    "百度", "抖音", "bilibili", "b站", "infoq", "csdn", "juejin", "sspai",
    "ithome", "ifanr", "geekpark", "qbitai", "jiqizhixin", "solidot", "v2ex",
    "huxiu", "36kr",
]


def _is_foreign(item):
    """判断是否为境外来源：先按内置境内源名单精确匹配，再按名称/语言线索兜底。"""
    src = (item.get("source") or "").strip()
    if src in DOMESTIC_SOURCES:
        return False
    src_l = src.lower()
    if any(h.lower() in src_l for h in DOMESTIC_HINTS):
        return False
    lang = (item.get("language") or "").lower()
    if lang in ("zh", "zh-cn", "zh_cn", "chinese"):
        return False
    if lang in ("en", "english"):
        return True
    # 未标注语言：绝大多数采集源为英文，默认按境外处理以放大信息差信号
    return True


def _hot(item):
    try:
        return int(item.get("hot_value") or 0)
    except (TypeError, ValueError):
        return 0


def _range_label(time_range):
    return {
        "week": "近 7 天", "month": "近 30 天", "quarter": "近 90 天",
        "year": "近 365 天", "all": "全部时间",
    }.get((time_range or "all").lower(), time_range or "全部时间")


def build_digest(items, category="全部", time_range="all"):
    if not items:
        return (
            "当前筛选条件下没有数据。\n\n"
            "请先在左侧点击「刷新全部」采集热点，或到「AI 设置 → 抓取来源」确认已开启相应采集源。"
        )

    total = len(items)
    cat_counter = {}
    for it in items:
        c = it.get("category") or "未分类"
        cat_counter[c] = cat_counter.get(c, 0) + 1
    sources = {(it.get("source") or "") for it in items}
    foreign = [it for it in items if _is_foreign(it)]
    pending = [it for it in items if not it.get("ai_report")]

    cat_heat = {}
    for it in items:
        c = it.get("category") or "未分类"
        cat_heat[c] = cat_heat.get(c, 0) + _hot(it)
    top_cats = sorted(cat_heat.items(), key=lambda x: x[1], reverse=True)[:6]

    scope = f"{category} · {_range_label(time_range)}"
    lines = [
        f"# 信息差洞察（{scope}）",
        "",
        "> 信息差 = 境外已在讨论、境内尚未充分覆盖的信号。下列内容基于本地已采集数据聚合，"
        "配置大模型 API Key 后可生成由真实模型撰写的深度分析。",
        "",
        "## 一、概览",
        "",
        f"- 热点条目：**{total}** 条",
        f"- 覆盖分类：**{len(cat_counter)}** 个",
        f"- 覆盖来源：**{len(sources)}** 个",
        f"- 境外来源条目：**{len(foreign)}** 条（信息差主要来源）",
        f"- 尚未生成分析：**{len(pending)}** 条",
        "",
        "## 二、分类热度排行（按热度聚合）",
        "",
    ]

    for idx, (c, heat) in enumerate(top_cats, 1):
        group = [it for it in items if (it.get("category") or "未分类") == c]
        group.sort(key=_hot, reverse=True)
        lines.append(f"{idx}. **{c}** — 热度聚合 {heat}，共 {len(group)} 条")
        for it in group[:3]:
            title = (it.get("title") or "").strip() or "(无标题)"
            url = it.get("url") or "#"
            lines.append(
                f"   - [{title}]({url}) — {it.get('source')} · 热度 {_hot(it)}"
            )
        lines.append("")

    candidates = [it for it in foreign if not it.get("ai_report")]
    candidates.sort(key=_hot, reverse=True)
    candidates = candidates[:8]
    lines.append("## 三、信息差候选（境外热 · 境内待分析）")
    lines.append("")
    lines.append("> 这些条目来自境外来源且热度较高，但尚未生成中文深度分析，可能存在信息差机会。")
    lines.append("")
    if candidates:
        for idx, it in enumerate(candidates, 1):
            title = (it.get("title") or "").strip() or "(无标题)"
            url = it.get("url") or "#"
            lines.append(
                f"{idx}. [{title}]({url}) — {it.get('source')} · 热度 {_hot(it)}"
            )
    else:
        lines.append("暂无符合条件的候选条目。")
    lines.append("")

    pending_top = sorted(pending, key=_hot, reverse=True)[:5]
    lines.append("## 四、建议优先分析")
    lines.append("")
    if pending_top:
        for idx, it in enumerate(pending_top, 1):
            title = (it.get("title") or "").strip() or "(无标题)"
            url = it.get("url") or "#"
            lines.append(
                f"{idx}. [{title}]({url}) — {it.get('source')} · 热度 {_hot(it)}"
            )
    else:
        lines.append("当前筛选条件下的高价值条目均已生成分析。")
    lines.append("")

    return "\n".join(lines)


def digest_stats(items, category="全部", time_range="all"):
    if not items:
        return {
            "total": 0, "categories": 0, "sources": 0,
            "foreign": 0, "pending": 0,
        }
    cat_counter = {(it.get("category") or "未分类") for it in items}
    sources = {(it.get("source") or "") for it in items}
    foreign = sum(1 for it in items if _is_foreign(it))
    pending = sum(1 for it in items if not it.get("ai_report"))
    return {
        "total": len(items),
        "categories": len(cat_counter),
        "sources": len(sources),
        "foreign": foreign,
        "pending": pending,
    }


def top_info_gap_candidates(items, limit=30):
    """境外来源、按热度排序的候选结构化列表（未分析优先），用于"信息差工作台"。"""
    candidates = [it for it in items if _is_foreign(it)]
    candidates.sort(key=lambda x: (0 if not x.get("ai_report") else 1, -_hot(x)))
    return [
        {
            "id": it.get("id"),
            "title": (it.get("title") or "").strip() or "(无标题)",
            "url": it.get("url") or "",
            "source": it.get("source") or "",
            "category": it.get("category") or "未分类",
            "hot_value": _hot(it),
            "analyzed": bool(it.get("ai_report")),
        }
        for it in candidates[:limit]
    ]


def info_gap_summary(items):
    if not items:
        return {"total": 0, "foreign": 0, "pending": 0, "candidates": 0}
    foreign = sum(1 for it in items if _is_foreign(it))
    pending = sum(1 for it in items if not it.get("ai_report"))
    candidates = sum(1 for it in items if _is_foreign(it) and not it.get("ai_report"))
    return {
        "total": len(items),
        "foreign": foreign,
        "pending": pending,
        "candidates": candidates,
    }


CLUSTER_STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "in", "is", "are", "for", "on", "with",
    "how", "why", "what", "new", "study", "report", "says", "after", "from", "at",
    "as", "by", "it", "this", "that", "be", "was", "were", "will", "can", "your",
    "about", "into", "up", "out", "over", "not", "but", "its", "has", "have",
    "best", "top", "vs", "using", "use", "get", "one", "two",
}


def cluster_events(items, threshold=0.25, limit=25):
    """按标题相似度聚合同一事件的多源报道，量化"信息差"信号。

    返回聚类列表（按信息差分降序），每个聚类含代表标题、来源覆盖、境内外分布与成员。
    """
    if not items:
        return []

    def tokenize(title):
        t = (title or "").lower()
        toks = {
            tok for tok in re.findall(r"[a-z0-9]+", t)
            if len(tok) >= 2 and tok not in CLUSTER_STOPWORDS
        }
        cn = re.sub(r"[\s\W_]+", "", re.sub(r"[a-z0-9]+", "", t))
        for i in range(len(cn) - 1):
            toks.add(cn[i:i + 2])
        return toks

    def sim(a, b):
        if not a or not b:
            return 0.0
        inter = len(a & b)
        if not inter:
            return 0.0
        return inter / len(a | b)

    ordered = sorted(items, key=_hot, reverse=True)
    groups = []
    for it in ordered:
        tk = tokenize(it.get("title", ""))
        best, best_sim = None, 0.0
        for g in groups:
            s = sim(tk, g["_tokens"])
            if s > best_sim:
                best_sim, best = s, g
        if best and best_sim >= threshold:
            best["members"].append(it)
            best["_tokens"] |= tk
            if _hot(it) > best["_maxhot"]:
                best["representative"] = (it.get("title") or "").strip() or "(无标题)"
                best["_maxhot"] = _hot(it)
        else:
            groups.append({
                "representative": (it.get("title") or "").strip() or "(无标题)",
                "_tokens": tk,
                "_maxhot": _hot(it),
                "members": [it],
            })

    result = []
    for g in groups:
        members = g["members"]
        foreign = [m for m in members if _is_foreign(m)]
        domestic = [m for m in members if not _is_foreign(m)]
        sources = []
        for m in members:
            s = m.get("source") or ""
            if s and s not in sources:
                sources.append(s)
        total_hot = sum(_hot(m) for m in members)
        coverage = len(sources)
        asym = max(0, len(foreign) - len(domestic))
        heat = math.log10(total_hot + 1)
        score = round((coverage + asym * 1.5) * heat * 10, 1)
        result.append({
            "representative": g["representative"],
            "coverage": coverage,
            "sources": sources,
            "overseas": len(foreign),
            "domestic": len(domestic),
            "total_hot": total_hot,
            "score": score,
            "members": [
                {
                    "id": m.get("id"),
                    "title": (m.get("title") or "").strip() or "(无标题)",
                    "source": m.get("source") or "",
                    "url": m.get("url") or "",
                    "hot_value": _hot(m),
                    "foreign": _is_foreign(m),
                }
                for m in members
            ],
        })

    result.sort(key=lambda x: (-x["score"], -x["total_hot"]))
    return result[:limit]
