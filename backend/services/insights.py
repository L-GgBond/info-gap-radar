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
