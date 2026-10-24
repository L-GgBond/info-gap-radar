import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(os.environ.get("INFO_GAP_HOME", str(Path.home() / ".info-gap-radar")))
DB_PATH = APP_DIR / "radar.sqlite3"

RANGE_DAYS = {"week": 7, "month": 30, "quarter": 90, "year": 365}

# 列表接口只取轻字段；正文/翻译/报告等大字段按需单独读取
# 列名带表前缀：FTS JOIN 时两个表都有 title/summary/content，避免歧义
LIST_COLUMNS = """
    hot_items.id, hot_items.source, hot_items.category, hot_items.title,
    hot_items.url, hot_items.hot_value, hot_items.hot_score, hot_items.summary,
    hot_items.item_date, hot_items.crawl_time, hot_items.favorite, hot_items.read,
    (hot_items.ai_report IS NOT NULL AND hot_items.ai_report != '') AS analyzed
"""

FLAG_COLUMNS = ("favorite", "read", "hidden")

# FTS 中文支持：unicode61 分词器不会切分连续汉字，子串搜不到。
# 索引与查询统一做 CJK 二元分词（bigram），由 Python 端注册的 cjkseg 函数完成。
FTS_VERSION = "2-cjkseg"


def cjk_segment(text):
    """把连续汉字串切成二元组、其余连续段原样保留：'AI 芯片融资' -> 'AI 芯片 片融 融资'。"""
    if not text:
        return text or ""
    out = []
    buf = []
    prev_cjk = None

    def flush():
        s = "".join(buf).strip()
        buf.clear()
        if not s:
            return
        if len(s) == 1 or not any(_is_cjk(ch) for ch in s):
            out.append(s)
        else:
            out.extend(s[i:i + 2] for i in range(len(s) - 1))

    for ch in text:
        is_cjk = _is_cjk(ch)
        if prev_cjk is not None and is_cjk != prev_cjk:
            flush()
        buf.append(ch)
        prev_cjk = is_cjk
    flush()
    return " ".join(out)


def _is_cjk(ch):
    return "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" or "\uac00" <= ch <= "\ud7af"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.create_function("cjkseg", 1, cjk_segment, deterministic=True)
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
                hot_score REAL DEFAULT 0,
                summary TEXT,
                raw_text TEXT,
                ai_report TEXT,
                content TEXT,
                language TEXT,
                translated TEXT,
                translation_engine TEXT,
                item_date TEXT,
                crawl_time TEXT NOT NULL,
                favorite INTEGER DEFAULT 0,
                read INTEGER DEFAULT 0,
                hidden INTEGER DEFAULT 0
            )
        """)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(hot_items)")}
        migrations = {
            "item_date": "ALTER TABLE hot_items ADD COLUMN item_date TEXT",
            "content": "ALTER TABLE hot_items ADD COLUMN content TEXT",
            "language": "ALTER TABLE hot_items ADD COLUMN language TEXT",
            "translated": "ALTER TABLE hot_items ADD COLUMN translated TEXT",
            "translation_engine": "ALTER TABLE hot_items ADD COLUMN translation_engine TEXT",
            "hot_score": "ALTER TABLE hot_items ADD COLUMN hot_score REAL DEFAULT 0",
            "favorite": "ALTER TABLE hot_items ADD COLUMN favorite INTEGER DEFAULT 0",
            "read": "ALTER TABLE hot_items ADD COLUMN read INTEGER DEFAULT 0",
            "hidden": "ALTER TABLE hot_items ADD COLUMN hidden INTEGER DEFAULT 0",
        }
        for col, ddl in migrations.items():
            if col not in cols:
                conn.execute(ddl)

        # 自定义 RSS 订阅源
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                category TEXT DEFAULT '科技',
                created_at TEXT NOT NULL
            )
        """)
        # 用户添加过的自定义站点（便于重复抓取与管理）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # FTS5 全文索引（外部内容表：触发器随 hot_items 增删改同步，中文经 cjkseg 切词）
        fts_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='items_fts'"
        ).fetchone()
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
                title, summary, content,
                content='hot_items', content_rowid='id'
            )
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS items_fts_ai AFTER INSERT ON hot_items BEGIN
                INSERT INTO items_fts(rowid, title, summary, content)
                VALUES (new.id, cjkseg(new.title), cjkseg(new.summary), cjkseg(new.content));
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS items_fts_ad AFTER DELETE ON hot_items BEGIN
                INSERT INTO items_fts(items_fts, rowid, title, summary, content)
                VALUES ('delete', old.id, cjkseg(old.title), cjkseg(old.summary), cjkseg(old.content));
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS items_fts_au AFTER UPDATE ON hot_items BEGIN
                INSERT INTO items_fts(items_fts, rowid, title, summary, content)
                VALUES ('delete', old.id, cjkseg(old.title), cjkseg(old.summary), cjkseg(old.content));
                INSERT INTO items_fts(rowid, title, summary, content)
                VALUES (new.id, cjkseg(new.title), cjkseg(new.summary), cjkseg(new.content));
            END
        """)
        # 分词方案变更或首次建索引：清空后按当前方案回填
        conn.execute("CREATE TABLE IF NOT EXISTS fts_meta (k TEXT PRIMARY KEY, v TEXT)")
        version = conn.execute("SELECT v FROM fts_meta WHERE k = 'version'").fetchone()
        if not fts_exists or not version or version[0] != FTS_VERSION:
            conn.execute("INSERT INTO items_fts(items_fts) VALUES('delete-all')")
            for row in conn.execute("SELECT id, title, summary, content FROM hot_items").fetchall():
                conn.execute(
                    "INSERT INTO items_fts(rowid, title, summary, content) VALUES (?, ?, ?, ?)",
                    [row["id"], cjk_segment(row["title"] or ""), cjk_segment(row["summary"] or ""),
                     cjk_segment(row["content"] or "")],
                )
            conn.execute(
                "INSERT INTO fts_meta (k, v) VALUES ('version', ?) "
                "ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                [FTS_VERSION],
            )


def save_items(items):
    """批量落库。ON CONFLICT 只刷新抓取侧字段，收藏/已读/隐藏/报告/正文不受影响。"""
    with connect() as conn:
        for item in items:
            conn.execute("""
                INSERT INTO hot_items (source, category, title, url, hot_value, hot_score,
                                       summary, raw_text, item_date, crawl_time)
                VALUES (:source, :category, :title, :url, :hot_value, :hot_score,
                        :summary, :raw_text, :item_date, :crawl_time)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title,
                    category=excluded.category,
                    hot_value=excluded.hot_value,
                    hot_score=excluded.hot_score,
                    summary=excluded.summary,
                    raw_text=excluded.raw_text,
                    item_date=excluded.item_date,
                    crawl_time=excluded.crawl_time
            """, item)


def _fts_query(q: str):
    """把用户输入转成安全的 FTS5 短语查询：按空白拆词、CJK 二元分词、逐词加引号 AND 连接。"""
    terms = []
    for raw in (q or "").split():
        term = raw.replace('"', '""').strip()
        if term:
            seg = cjk_segment(term)
            if seg.strip():
                terms.append(seg)
    if not terms:
        return None
    return " AND ".join(f'"{t}"' for t in terms)


def list_items(category=None, time_range=None, q=None, favorite=None,
               limit=500, offset=0, include_hidden=False):
    conds, params = [], []
    if category and category != "全部":
        conds.append("hot_items.category = ?")
        params.append(category)
    days = RANGE_DAYS.get((time_range or "").lower())
    if days:
        conds.append("COALESCE(hot_items.item_date, hot_items.crawl_time) >= ?")
        params.append((datetime.now(timezone.utc) - timedelta(days=days)).isoformat())
    if not include_hidden:
        conds.append("hot_items.hidden = 0")
    if favorite:
        conds.append("hot_items.favorite = 1")
    fts = _fts_query(q)
    join = ""
    if fts:
        join = "JOIN items_fts ON hot_items.id = items_fts.rowid"
        conds.append("items_fts MATCH ?")
        params.append(fts)
    query = f"SELECT {LIST_COLUMNS} FROM hot_items {join}"
    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += (" ORDER BY hot_items.hot_score DESC, "
              "COALESCE(hot_items.item_date, hot_items.crawl_time) DESC LIMIT ? OFFSET ?")
    params += [int(limit), int(offset)]
    with connect() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_item(item_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM hot_items WHERE id = ?", [item_id]).fetchone()
        return dict(row) if row else None


def get_ids_by_urls(urls):
    """按 URL 批量查 id 与正文缓存状态（后台预抓全文用）。"""
    out = {}
    url_list = [u for u in urls if u]
    with connect() as conn:
        for i in range(0, len(url_list), 100):
            chunk = url_list[i:i + 100]
            marks = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT id, url, content FROM hot_items WHERE url IN ({marks})", chunk
            ).fetchall()
            for row in rows:
                out[row["url"]] = {"id": row["id"], "has_content": bool(row["content"])}
    return out


def set_flags(item_id, flags):
    """白名单更新 favorite / read / hidden 标记，返回是否更新到行。"""
    sets = {k: int(bool(v)) for k, v in flags.items() if k in FLAG_COLUMNS}
    if not sets:
        return False
    clause = ", ".join(f"{k} = ?" for k in sets)
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE hot_items SET {clause} WHERE id = ?",
            [*sets.values(), item_id],
        )
        return cur.rowcount > 0


def save_report(item_id, markdown):
    with connect() as conn:
        conn.execute("UPDATE hot_items SET ai_report = ? WHERE id = ?", [markdown, item_id])


def save_content(item_id, content, language, translated, translation_engine):
    with connect() as conn:
        conn.execute(
            "UPDATE hot_items SET content = ?, language = ?, translated = ?, translation_engine = ? WHERE id = ?",
            [content, language, translated, translation_engine, item_id],
        )


def purge_old_items(days=None):
    """删除超过保留期的非收藏条目，返回删除数量。"""
    try:
        days = int(days or 180)
    except (TypeError, ValueError):
        days = 180
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM hot_items WHERE favorite = 0 AND COALESCE(item_date, crawl_time) < ?",
            [cutoff],
        )
        return cur.rowcount


# ===== 自定义订阅源 =====

def list_custom_feeds():
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM custom_feeds ORDER BY id DESC"
        ).fetchall()]


def upsert_custom_feed(name, url, category="科技"):
    with connect() as conn:
        conn.execute("""
            INSERT INTO custom_feeds (name, url, category, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET name=excluded.name, category=excluded.category
        """, [name, url, category, datetime.now(timezone.utc).isoformat()])


def delete_custom_feed(feed_id):
    with connect() as conn:
        return conn.execute("DELETE FROM custom_feeds WHERE id = ?", [feed_id]).rowcount > 0


def find_custom_feed(feed_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM custom_feeds WHERE id = ?", [feed_id]).fetchone()
        return dict(row) if row else None


# ===== 自定义站点 =====

def list_custom_sites():
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM custom_sites ORDER BY id DESC"
        ).fetchall()]


def upsert_custom_site(url, title=None):
    with connect() as conn:
        conn.execute("""
            INSERT INTO custom_sites (url, title, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET title=COALESCE(excluded.title, custom_sites.title)
        """, [url, title, datetime.now(timezone.utc).isoformat()])


def delete_custom_site(site_id):
    with connect() as conn:
        return conn.execute("DELETE FROM custom_sites WHERE id = ?", [site_id]).rowcount > 0
