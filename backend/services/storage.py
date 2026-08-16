import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path.home() / ".info-gap-radar" / "radar.sqlite3"

RANGE_DAYS = {"week": 7, "month": 30, "quarter": 90, "year": 365}


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hot_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                hot_value INTEGER DEFAULT 0,
                summary TEXT,
                raw_text TEXT,
                ai_report TEXT,
                content TEXT,
                language TEXT,
                translated TEXT,
                translation_engine TEXT,
                item_date TEXT,
                crawl_time TEXT NOT NULL
            )
        """)
        # 兼容旧库：为已存在的表补齐新增列
        cols = {row[1] for row in conn.execute("PRAGMA table_info(hot_items)")}
        migrations = {
            "item_date": "ALTER TABLE hot_items ADD COLUMN item_date TEXT",
            "content": "ALTER TABLE hot_items ADD COLUMN content TEXT",
            "language": "ALTER TABLE hot_items ADD COLUMN language TEXT",
            "translated": "ALTER TABLE hot_items ADD COLUMN translated TEXT",
            "translation_engine": "ALTER TABLE hot_items ADD COLUMN translation_engine TEXT",
        }
        for col, ddl in migrations.items():
            if col not in cols:
                conn.execute(ddl)


def save_items(items):
    with connect() as conn:
        for item in items:
            conn.execute("""
                INSERT INTO hot_items (source, category, title, url, hot_value, summary, raw_text, item_date, crawl_time)
                VALUES (:source, :category, :title, :url, :hot_value, :summary, :raw_text, :item_date, :crawl_time)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title,
                    hot_value=excluded.hot_value,
                    summary=excluded.summary,
                    raw_text=excluded.raw_text,
                    item_date=excluded.item_date,
                    crawl_time=excluded.crawl_time
            """, item)


def list_items(category=None, time_range=None):
    query = "SELECT * FROM hot_items"
    conds, params = [], []
    if category and category != "全部":
        conds.append("category = ?")
        params.append(category)
    days = RANGE_DAYS.get((time_range or "").lower())
    if days:
        conds.append("COALESCE(item_date, crawl_time) >= ?")
        params.append((datetime.now(timezone.utc) - timedelta(days=days)).isoformat())
    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY hot_value DESC, item_date DESC LIMIT 500"
    with connect() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_item(item_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM hot_items WHERE id = ?", [item_id]).fetchone()
        return dict(row) if row else None


def save_report(item_id, markdown):
    with connect() as conn:
        conn.execute("UPDATE hot_items SET ai_report = ? WHERE id = ?", [markdown, item_id])


def save_content(item_id, content, language, translated, translation_engine):
    with connect() as conn:
        conn.execute(
            "UPDATE hot_items SET content = ?, language = ?, translated = ?, translation_engine = ? WHERE id = ?",
            [content, language, translated, translation_engine, item_id],
        )
