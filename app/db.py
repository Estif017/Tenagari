"""SQLite setup and queries. Only the mistakes table for now; more in Step 3."""

import sqlite3
from datetime import date
from pathlib import Path

from app.config import ROOT
from app.schemas import Correction, ReadingText

DB_PATH = ROOT / "data" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS mistakes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    source      TEXT NOT NULL,
    category    TEXT NOT NULL,
    subcategory TEXT,
    original    TEXT NOT NULL,
    corrected   TEXT NOT NULL,
    explanation TEXT
);

-- Reading texts generated ahead of time so a session starts instantly.
CREATE TABLE IF NOT EXISTS reading_queue (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created    TEXT NOT NULL,
    topic      TEXT NOT NULL,
    title      TEXT NOT NULL,
    text       TEXT NOT NULL
);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open the database, creating the file and tables if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_mistakes(corrections: list[Correction], source: str, path: Path = DB_PATH) -> int:
    """Insert corrections into the mistakes table. Returns how many were saved."""
    today = date.today().isoformat()
    rows = [(today, source, c.category, c.original, c.corrected, c.reason) for c in corrections]
    conn = connect(path)
    try:
        with conn:  # commits on success, rolls back on error
            conn.executemany(
                "INSERT INTO mistakes (date, source, category, original, corrected, explanation) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
    finally:
        conn.close()
    return len(rows)


def queue_reading(topic: str, passage: ReadingText, path: Path = DB_PATH) -> None:
    """Store a pre-generated reading text for a future session."""
    conn = connect(path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO reading_queue (created, topic, title, text) VALUES (?, ?, ?, ?)",
                (date.today().isoformat(), topic, passage.title, passage.text),
            )
    finally:
        conn.close()


def pop_reading(path: Path = DB_PATH) -> tuple[str, ReadingText] | None:
    """Remove and return the oldest queued text as (topic, passage), or None if empty."""
    conn = connect(path)
    try:
        with conn:
            row = conn.execute("SELECT * FROM reading_queue ORDER BY id LIMIT 1").fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM reading_queue WHERE id = ?", (row["id"],))
    finally:
        conn.close()
    return row["topic"], ReadingText(title=row["title"], text=row["text"])


def reading_queue_size(path: Path = DB_PATH) -> int:
    """How many pre-generated texts are waiting."""
    conn = connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM reading_queue").fetchone()[0]
    finally:
        conn.close()
