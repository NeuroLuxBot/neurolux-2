import sqlite3
from typing import Optional, Any, List, Tuple

DB_PATH = "neurolux.db"

def connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS free_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            niche TEXT,
            tiktok_link TEXT,
            goal TEXT,
            material_type TEXT,
            material_value TEXT,
            day INTEGER DEFAULT 1,
            is_done INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            test_id INTEGER,
            day INTEGER,
            post_link TEXT,
            views INTEGER,
            likes INTEGER,
            comments INTEGER,
            follows INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            plan TEXT,
            status TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.commit()

def upsert_user(user_id: int, username: Optional[str]):
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES (?,?)", (user_id, username))
        if username:
            con.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        con.commit()

def start_free_test(user_id: int):
    with connect() as con:
        con.execute("UPDATE free_tests SET is_done=1 WHERE user_id=? AND is_done=0", (user_id,))
        con.execute("INSERT INTO free_tests(user_id) VALUES (?)", (user_id,))
        con.commit()

def get_active_test_id(user_id: int) -> Optional[int]:
    with connect() as con:
        row = con.execute(
            "SELECT id FROM free_tests WHERE user_id=? AND is_done=0 ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        return row[0] if row else None

def update_test_field(user_id: int, field: str, value: Any):
    test_id = get_active_test_id(user_id)
    if not test_id:
        return
    with connect() as con:
        con.execute(f"UPDATE free_tests SET {field}=? WHERE id=?", (value, test_id))
        con.commit()

def get_test_day(user_id: int) -> int:
    test_id = get_active_test_id(user_id)
    if not test_id:
        return 1
    with connect() as con:
        row = con.execute("SELECT day FROM free_tests WHERE id=?", (test_id,)).fetchone()
        return int(row[0]) if row else 1

def set_test_day(user_id: int, day: int):
    update_test_field(user_id, "day", day)

def finish_test(user_id: int):
    test_id = get_active_test_id(user_id)
    if not test_id:
        return
    with connect() as con:
        con.execute("UPDATE free_tests SET is_done=1 WHERE id=?", (test_id,))
        con.commit()

def get_last_test_fields(user_id: int) -> dict:
    with connect() as con:
        row = con.execute("""
            SELECT id, niche, tiktok_link, goal
            FROM free_tests
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 1
        """, (user_id,)).fetchone()
        if not row:
            return {}
        return {"test_id": row[0], "niche": row[1], "tiktok_link": row[2], "goal": row[3]}

def add_stats(user_id: int, day: int, post_link: str, views: int, likes: int, comments: int, follows: int):
    test_id = get_active_test_id(user_id)
    if not test_id:
        with connect() as con:
            row = con.execute("SELECT id FROM free_tests WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
            test_id = row[0] if row else None

    with connect() as con:
        con.execute("""
        INSERT INTO stats(user_id, test_id, day, post_link, views, likes, comments, follows)
        VALUES (?,?,?,?,?,?,?,?)
        """, (user_id, test_id, day, post_link, views, likes, comments, follows))
        con.commit()

def get_stats_for_last_test(user_id: int) -> List[Tuple]:
    with connect() as con:
        row = con.execute("SELECT id FROM free_tests WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
        if not row:
            return []
        test_id = row[0]
        return con.execute("""
            SELECT day, post_link, views, likes, comments, follows
            FROM stats
            WHERE user_id=? AND test_id=?
            ORDER BY day ASC
        """, (user_id, test_id)).fetchall()

def set_subscription(user_id: int, plan: str, status: str):
    with connect() as con:
        con.execute("""
        INSERT INTO subscriptions(user_id, plan, status) VALUES (?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET plan=excluded.plan, status=excluded.status, updated_at=CURRENT_TIMESTAMP
        """, (user_id, plan, status))
        con.commit()
