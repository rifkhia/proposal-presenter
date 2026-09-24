import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DATA_DIR

DB_PATH = DATA_DIR / "comments.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal    TEXT NOT NULL,
    author      TEXT NOT NULL,
    body        TEXT NOT NULL,
    quote       TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_comments_proposal ON comments (proposal);
"""


def init_db() -> None:
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
