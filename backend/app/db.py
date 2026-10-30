import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DATA_DIR

DB_PATH = DATA_DIR / "comments.db"

# A comment with parent_id NULL starts a thread; replies point at it. Only
# threads carry an anchor (quote + source line range) and a resolved state.
SCHEMA = """
CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal    TEXT NOT NULL,
    author      TEXT NOT NULL,
    body        TEXT NOT NULL,
    quote       TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    parent_id   INTEGER,
    line_start  INTEGER,
    line_end    INTEGER,
    resolved    INTEGER NOT NULL DEFAULT 0,
    resolved_by TEXT,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_comments_proposal ON comments (proposal);

-- Last version of each proposal the server has seen; see anchoring.py.
CREATE TABLE IF NOT EXISTS snapshots (
    proposal    TEXT PRIMARY KEY,
    version     TEXT NOT NULL,
    content     TEXT NOT NULL
);

-- Who uploaded each proposal; only they can delete it. Files copied in on the
-- server have no row, so nobody can delete them from the app.
CREATE TABLE IF NOT EXISTS owners (
    proposal    TEXT PRIMARY KEY,
    username    TEXT NOT NULL
);

-- Editor accounts; see auth.py. Only the PBKDF2 hash of the password is stored.
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""

# Columns added after the first release. Databases created before them get the
# columns on startup, so existing rows are kept.
ADDED_COLUMNS = {
  "comments": {
    "parent_id": "INTEGER",
    "line_start": "INTEGER",
    "line_end": "INTEGER",
    "resolved": "INTEGER NOT NULL DEFAULT 0",
    "resolved_by": "TEXT",
    "resolved_at": "TEXT",
    # Account that posted the comment, if any; only it can delete the comment.
    "owner": "TEXT",
  },
  "users": {
    # Admins may delete any proposal or comment. Set with `python -m app.makeadmin`.
    "is_admin": "INTEGER NOT NULL DEFAULT 0",
  },
}

NOW = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"


def init_db() -> None:
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        for table, columns in ADDED_COLUMNS.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, ddl in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_parent ON comments (parent_id)")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
