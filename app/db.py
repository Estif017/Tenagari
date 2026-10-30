"""SQLite setup and queries. Only the mistakes table for now; more in Step 3."""

import sqlite3
from datetime import date
from pathlib import Path

from app.config import ROOT
from app.schemas import Correction

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
