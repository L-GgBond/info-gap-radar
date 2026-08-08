import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".info-gap-radar" / "radar.sqlite3"


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
                crawl_time TEXT NOT NULL
            )
        """)


def save_items(items):
    with connect() as conn:
        for item in items:
            conn.execute("""
                INSERT INTO hot_items (source, category, title, url, hot_value, summary, raw_text, crawl_time)
                VALUES (:source, :category, :title, :url, :hot_value, :summary, :raw_text, :crawl_time)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title,
                    hot_value=excluded.hot_value,
                    summary=excluded.summary,
                    raw_text=excluded.raw_text,
                    crawl_time=excluded.crawl_time
            """, item)


def list_items(category=None):
    query = "SELECT * FROM hot_items"
    params = []
    if category and category != "全部":
        query += " WHERE category = ?"
        params.append(category)
    query += " ORDER BY hot_value DESC, crawl_time DESC LIMIT 120"
    with connect() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_item(item_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM hot_items WHERE id = ?", [item_id]).fetchone()
        return dict(row) if row else None


def save_report(item_id, markdown):
    with connect() as conn:
        conn.execute("UPDATE hot_items SET ai_report = ? WHERE id = ?", [markdown, item_id])
