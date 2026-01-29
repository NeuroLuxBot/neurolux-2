import os
import sqlite3
from typing import Optional, Any, List, Tuple

# Must-have: persistent DB path for Railway Volume
DEFAULT_DB_PATH = os.getenv("DB_PATH", "/data/neurolux.db")
FALLBACK_DB_PATH = "neurolux.db"

# Разрешенные поля для безопасного update_test_field
# ✅ ДОБАВЛЕНО: material_video_id, material_description
ALLOWED_TEST_FIELDS = {
    "niche",
    "tiktok_link",
    "goal",
    "material_type",
    "material_value",
    "material_video_id",
    "material_description",
    "day",
    "is_done",
}

_conn: Optional[sqlite3.Connection] = None


def _ensure_dir_for(path: str) -> None:
    if os.path.isabs(path):
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn

    try:
        _ensure_dir_for(DEFAULT_DB_PATH)
        _conn = sqlite3.connect(DEFAULT_DB_PATH, check_same_thread=False)
    except Exception:
        _conn = sqlite3.connect(FALLBACK_DB_PATH, check_same_thread=False)

    _conn.row_factory = sqlite3.Row

    try:
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass

    return _conn


def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _ensure_free_tests_columns(con: sqlite3.Connection) -> None:
    """
    ✅ Мягкая миграция: добавляет недостающие колонки в free_tests,
    чтобы не ломать уже существующую БД.
    """
    try:
        if not _column_exists(con, "free_tests", "material_video_id"):
            con.execute("ALTER TABLE free_tests ADD COLUMN material_video_id TEXT;")
        if not _column_exists(con, "free_tests", "material_description"):
            con.execute("ALTER TABLE free_tests ADD COLUMN material_description TEXT;")
        con.commit()
    except Exception:
        # если таблицы ещё нет или ALTER не прошёл — просто пропускаем
        pass


def init_db() -> None:
    con = connect()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # ✅ ДОБАВЛЕНО в схему: material_video_id, material_description
    cur.execute("""
    CREATE TABLE IF NOT EXISTS free_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        niche TEXT,
        tiktok_link TEXT,
        goal TEXT,
        material_type TEXT,
        material_value TEXT,
        material_video_id TEXT,
        material_description TEXT,
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

    # ✅ Миграция для старых БД
    _ensure_free_tests_columns(con)


def upsert_user(user_id: int, username: Optional[str]) -> None:
    con = connect()
    con.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES (?,?)", (user_id, username))
    if username:
        con.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
    con.commit()


def start_free_test(user_id: int) -> None:
    con = connect()
    con.execute("UPDATE free_tests SET is_done=1 WHERE user_id=? AND is_done=0", (user_id,))
    con.execute("INSERT INTO free_tests(user_id) VALUES (?)", (user_id,))
    con.commit()


def get_active_test_id(user_id: int) -> Optional[int]:
    con = connect()
    row = con.execute(
        "SELECT id FROM free_tests WHERE user_id=? AND is_done=0 ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return int(row["id"]) if row else None


def update_test_field(user_id: int, field: str, value: Any) -> None:
    if field not in ALLOWED_TEST_FIELDS:
        return

    test_id = get_active_test_id(user_id)
    if not test_id:
        return

    con = connect()
    con.execute(f"UPDATE free_tests SET {field}=? WHERE id=?", (value, test_id))
    con.commit()


def get_test_day(user_id: int) -> int:
    test_id = get_active_test_id(user_id)
    if not test_id:
        return 1

    con = connect()
    row = con.execute("SELECT day FROM free_tests WHERE id=?", (test_id,)).fetchone()
    return int(row["day"]) if row and row["day"] is not None else 1


def set_test_day(user_id: int, day: int) -> None:
    update_test_field(user_id, "day", day)


def finish_test(user_id: int) -> None:
    test_id = get_active_test_id(user_id)
    if not test_id:
        return
    con = connect()
    con.execute("UPDATE free_tests SET is_done=1 WHERE id=?", (test_id,))
    con.commit()


def get_last_test_fields(user_id: int) -> dict:
    con = connect()
    row = con.execute(
        """
        SELECT id, niche, tiktok_link, goal,
               material_type, material_value, material_video_id, material_description
        FROM free_tests
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()

    if not row:
        return {}

    return {
        "test_id": int(row["id"]),
        "niche": row["niche"],
        "tiktok_link": row["tiktok_link"],
        "goal": row["goal"],
        # ✅ полезно для админ-уведомлений/логов
        "material_type": row["material_type"],
        "material_value": row["material_value"],
        "material_video_id": row["material_video_id"],
        "material_description": row["material_description"],
    }


def add_stats(user_id: int, day: int, post_link: str, views: int, likes: int, comments: int, follows: int) -> None:
    test_id = get_active_test_id(user_id)

    if not test_id:
        con = connect()
        row = con.execute(
            "SELECT id FROM free_tests WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        test_id = int(row["id"]) if row else None

    con = connect()
    con.execute(
        """
        INSERT INTO stats(user_id, test_id, day, post_link, views, likes, comments, follows)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (user_id, test_id, day, post_link, views, likes, comments, follows),
    )
    con.commit()


def get_stats_for_last_test(user_id: int) -> List[Tuple]:
    con = connect()
    row = con.execute(
        "SELECT id FROM free_tests WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()

    if not row:
        return []

    test_id = int(row["id"])
    rows = con.execute(
        """
        SELECT day, post_link, views, likes, comments, follows
        FROM stats
        WHERE user_id=? AND test_id=?
        ORDER BY day ASC
        """,
        (user_id, test_id),
    ).fetchall()

    return [tuple(r) for r in rows]


def set_subscription(user_id: int, plan: str, status: str) -> None:
    con = connect()
    con.execute(
        """
        INSERT INTO subscriptions(user_id, plan, status)
        VALUES (?,?,?)
        ON CONFLICT(user_id) DO UPDATE
        SET plan=excluded.plan, status=excluded.status, updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, plan, status),
    )
    con.commit()
