"""SQLite setup and queries."""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from app.config import ROOT
from app.schemas import CheckedItem, Correction, ReadingText

DB_PATH = Path(os.environ.get("TENAGARI_DB", ROOT / "data" / "app.db"))  # env override for testing
RETIRE_AFTER = 3  # correct uses before a word counts as learned

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

CREATE TABLE IF NOT EXISTS words (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    word                 TEXT NOT NULL UNIQUE COLLATE NOCASE,
    example              TEXT,
    added_date           TEXT NOT NULL,
    times_used_correctly INTEGER NOT NULL DEFAULT 0,
    retired              INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quiz_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    date           TEXT NOT NULL,
    category       TEXT NOT NULL,
    kind           TEXT NOT NULL,
    question       TEXT NOT NULL,
    user_answer    TEXT NOT NULL,
    correct_answer TEXT NOT NULL,
    is_correct     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS recordings (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL  -- placement, daily, final
);

-- Checked quiz items generated ahead of time (JSON list of QuizItem).
CREATE TABLE IF NOT EXISTS quiz_queue (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    items   TEXT NOT NULL
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


@contextmanager
def open_db(path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Connection that commits on success, rolls back on error, and always closes."""
    conn = connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def today() -> str:
    return date.today().isoformat()


# --- Mistakes ---------------------------------------------------------------

def save_mistakes(corrections: list[Correction], source: str, path: Path = DB_PATH) -> int:
    """Insert corrections into the mistakes table. Returns how many were saved."""
    rows = [(today(), source, c.category, c.original, c.corrected, c.reason) for c in corrections]
    with open_db(path) as conn:
        conn.executemany(
            "INSERT INTO mistakes (date, source, category, original, corrected, explanation) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def top_mistake_categories(days: int = 7, limit: int = 3, path: Path = DB_PATH) -> list[tuple[str, int]]:
    """Most frequent mistake categories in the last `days` days, as (category, count)."""
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    with open_db(path) as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) AS n FROM mistakes WHERE date >= ? "
            "GROUP BY category ORDER BY n DESC, category LIMIT ?",
            (since, limit),
        ).fetchall()
    return [(r["category"], r["n"]) for r in rows]


def recent_mistakes(category: str, limit: int = 1, path: Path = DB_PATH) -> list[sqlite3.Row]:
    """The most recent mistakes in a category, newest first."""
    with open_db(path) as conn:
        return conn.execute(
            "SELECT * FROM mistakes WHERE category = ? ORDER BY id DESC LIMIT ?", (category, limit)
        ).fetchall()


def latest_mistake(category: str, path: Path = DB_PATH) -> sqlite3.Row | None:
    """The most recent mistake in a category (to show as an example)."""
    rows = recent_mistakes(category, limit=1, path=path)
    return rows[0] if rows else None


# --- Quiz -------------------------------------------------------------------

def save_quiz_result(category: str, kind: str, question: str, user_answer: str,
                     correct_answer: str, is_correct: bool, path: Path = DB_PATH) -> None:
    """Log one answered quiz question."""
    with open_db(path) as conn:
        conn.execute(
            "INSERT INTO quiz_results (date, category, kind, question, user_answer, correct_answer, is_correct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (today(), category, kind, question, user_answer, correct_answer, int(is_correct)),
        )


# --- Word bank --------------------------------------------------------------

def add_word(word: str, example: str | None = None, path: Path = DB_PATH) -> bool:
    """Add a word or phrase to the bank. Returns False if it's already there."""
    with open_db(path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO words (word, example, added_date) VALUES (?, ?, ?)",
            (word.strip(), example, today()),
        )
    return cur.rowcount == 1


def list_words(include_retired: bool = False, path: Path = DB_PATH) -> list[sqlite3.Row]:
    """All words, active first, newest first."""
    where = "" if include_retired else "WHERE retired = 0"
    with open_db(path) as conn:
        return conn.execute(f"SELECT * FROM words {where} ORDER BY retired, id DESC").fetchall()


def practice_words(n: int = 2, path: Path = DB_PATH) -> list[sqlite3.Row]:
    """Pick `n` active words to practice: least-used first, random among ties."""
    with open_db(path) as conn:
        return conn.execute(
            "SELECT * FROM words WHERE retired = 0 ORDER BY times_used_correctly, RANDOM() LIMIT ?",
            (n,),
        ).fetchall()


def record_correct_use(word: str, path: Path = DB_PATH) -> bool:
    """Count one correct use. Returns True if the word just got retired (learned)."""
    with open_db(path) as conn:
        conn.execute(
            "UPDATE words SET times_used_correctly = times_used_correctly + 1, "
            "retired = (times_used_correctly + 1 >= ?) WHERE word = ?",
            (RETIRE_AFTER, word),
        )
        row = conn.execute("SELECT times_used_correctly FROM words WHERE word = ?", (word,)).fetchone()
    return row is not None and row[0] == RETIRE_AFTER


def queue_quiz(items: list[CheckedItem], path: Path = DB_PATH) -> None:
    """Store checked quiz items for a future session."""
    payload = json.dumps([item.model_dump() for item in items])
    with open_db(path) as conn:
        conn.execute("INSERT INTO quiz_queue (created, items) VALUES (?, ?)", (today(), payload))


def pop_quiz(path: Path = DB_PATH) -> list[CheckedItem] | None:
    """Remove and return the oldest queued quiz, or None if empty."""
    with open_db(path) as conn:
        row = conn.execute("SELECT * FROM quiz_queue ORDER BY id LIMIT 1").fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM quiz_queue WHERE id = ?", (row["id"],))
    return [CheckedItem.model_validate(item) for item in json.loads(row["items"])]


def quiz_queue_size(path: Path = DB_PATH) -> int:
    """How many pre-generated quizzes are waiting."""
    with open_db(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM quiz_queue").fetchone()[0]


# --- Recordings -------------------------------------------------------------

def save_recording(file: Path, kind: str = "daily", path: Path = DB_PATH) -> None:
    """Log a saved audio file so we can play it back later (e.g. Day 1 vs today)."""
    with open_db(path) as conn:
        conn.execute("INSERT INTO recordings (date, path, kind) VALUES (?, ?, ?)", (today(), str(file), kind))


# --- Reading queue ----------------------------------------------------------

def queue_reading(topic: str, passage: ReadingText, path: Path = DB_PATH) -> None:
    """Store a pre-generated reading text for a future session."""
    with open_db(path) as conn:
        conn.execute(
            "INSERT INTO reading_queue (created, topic, title, text) VALUES (?, ?, ?, ?)",
            (today(), topic, passage.title, passage.text),
        )


def pop_reading(path: Path = DB_PATH) -> tuple[str, ReadingText] | None:
    """Remove and return the oldest queued text as (topic, passage), or None if empty."""
    with open_db(path) as conn:
        row = conn.execute("SELECT * FROM reading_queue ORDER BY id LIMIT 1").fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM reading_queue WHERE id = ?", (row["id"],))
    return row["topic"], ReadingText(title=row["title"], text=row["text"])


def reading_queue_size(path: Path = DB_PATH) -> int:
    """How many pre-generated texts are waiting."""
    with open_db(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM reading_queue").fetchone()[0]
