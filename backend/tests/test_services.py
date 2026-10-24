"""核心纯函数与存储层的单元测试。

运行：cd backend && .venv/Scripts/python.exe -m pytest tests -q
（Windows 下也可用 npm run backend:test）
"""
import os
import tempfile

import pytest

# 必须在导入 services 之前隔离数据目录
os.environ["INFO_GAP_HOME"] = tempfile.mkdtemp(prefix="igr-test-")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import collectors, insights, storage  # noqa: E402
from services.llm import _fulltext_section  # noqa: E402


@pytest.fixture()
def db():
    storage.init_db()
    # 每个用例独立数据，避免 AUTOINCREMENT id 相互影响
    with storage.connect() as conn:
        conn.execute("DELETE FROM hot_items")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='hot_items'")
    yield


def _item(**overrides):
    base = {
        "source": "Hacker News", "category": "科技", "title": "Rust 2.0 released",
        "url": "https://example.com/1", "hot_value": 100, "summary": "big release",
        "raw_text": "big release", "item_date": "2026-10-24T00:00:00+00:00",
        "crawl_time": "2026-10-24T00:00:00+00:00", "hot_score": 0.0,
    }
    base.update(overrides)
    return base


def test_normalize_hot_scores_cross_source():
    items = [
        _item(source="Hacker News", hot_value=300),
        _item(source="Hacker News", hot_value=100),
        _item(source="36氪", hot_value=0),
        _item(source="36氪", hot_value=0),
    ]
    collectors.normalize_hot_scores(items)
    assert items[0]["hot_score"] == 100.0
    assert items[1]["hot_score"] == 0.0
    # 同源同热度 → 按新旧给分
    assert items[2]["hot_score"] == 100.0
    assert items[3]["hot_score"] == 0.0


def test_is_foreign_with_domestic_sources():
    assert insights._is_foreign(_item(source="Hacker News")) is True
    assert insights._is_foreign(_item(source="36氪")) is False
    assert insights._is_foreign(_item(source="机器之心")) is False
    assert insights._is_foreign(_item(source="微博热搜")) is False


def test_cluster_events_merges_same_event():
    items = [
        _item(title="OpenAI launches new model gpt-5", hot_value=500),
        _item(title="OpenAI launches new model gpt-5 for enterprise", hot_value=200),
        _item(title="完全无关的另一个话题", source="36氪", hot_value=10),
    ]
    clusters = insights.cluster_events(items)
    assert len(clusters) == 2
    top = max(clusters, key=lambda c: len(c["members"]))
    assert len(top["members"]) == 2
    assert top["coverage"] == 1


def test_opml_roundtrip():
    feeds = [
        {"name": "阮一峰", "url": "https://ruanyifeng.com/blog/atom.xml", "category": "编程开发"},
        {"name": "A&B", "url": "https://a.com/rss?x=1&y=2", "category": "科技"},
    ]
    xml = collectors.export_opml(feeds)
    parsed = collectors.parse_opml(xml)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "阮一峰"
    assert parsed[1]["url"] == "https://a.com/rss?x=1&y=2"
    assert parsed[1]["category"] == "科技"


def test_fts_query_is_phrase_safe():
    # 按空白拆词、逐词加引号，注入词被当作普通短语处理
    assert storage._fts_query('rust OR "hack') == '"rust" AND "OR" AND """hack"'
    assert storage._fts_query("  ") is None


def test_cjk_segment():
    assert storage.cjk_segment("AI 芯片融资") == "AI 芯片 片融 融资"
    assert storage.cjk_segment("rust") == "rust"
    assert storage.cjk_segment("芯片") == "芯片"
    assert storage.cjk_segment("") == ""


def test_storage_roundtrip_and_flags(db):
    storage.save_items([
        _item(),
        _item(title="AI 芯片融资", source="36氪", category="创业与商业", url="https://example.com/2", hot_value=0, hot_score=50.0),
    ])
    storage.set_flags(1, {"favorite": True, "read": True})
    # 重新抓取（upsert）不丢标记
    storage.save_items([_item()])
    assert storage.get_item(1)["favorite"] == 1

    assert len(storage.list_items(favorite=True)) == 1
    assert len(storage.list_items(q="芯片")) == 1
    assert len(storage.list_items(q="rust 2.0")) == 1

    # 隐藏后默认列表不可见
    storage.set_flags(2, {"hidden": True})
    assert len(storage.list_items()) == 1
    assert len(storage.list_items(include_hidden=True)) == 2


def test_purge_keeps_favorites(db):
    storage.save_items([_item(), _item(url="https://example.com/old", item_date="2020-01-01T00:00:00+00:00", crawl_time="2020-01-01T00:00:00+00:00")])
    storage.set_flags(1, {"favorite": True})
    purged = storage.purge_old_items(180)
    assert purged == 1
    assert storage.get_item(1) is not None
    assert storage.get_item(2) is None


def test_fulltext_section_truncates():
    assert _fulltext_section({"content": ""}) == ""
    section = _fulltext_section({"content": "A" * 9000})
    assert "正文过长已截断" in section
    assert section.index("…（正文过长") == 8015
