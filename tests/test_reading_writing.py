"""Tests for the feedback schema and saving mistakes (no LLM needed)."""

import sqlite3

from app.db import save_mistakes
from app.schemas import Correction, WritingFeedback


def make_correction(category: str = "article") -> dict:
    # a fix the diff rule can't classify, so the given category is kept
    return {"original": "he said me", "corrected": "he told me",
            "category": category, "reason": "'say' doesn't take a person as object."}


def test_unknown_category_becomes_other():
    assert Correction(**make_correction("Grammar")).category == "other"
    assert Correction(**make_correction("Word Order")).category == "word_order"


def test_feedback_keeps_max_three_corrections():
    fb = WritingFeedback(summary_score=7, corrections=[make_correction()] * 5,
                         better_phrases=[], encouragement="Nice work!")
    assert len(fb.corrections) == 3


def test_save_mistakes_writes_rows(tmp_path):
    db = tmp_path / "test.db"
    corrections = [Correction(**make_correction()), Correction(**make_correction("tense"))]
    assert save_mistakes(corrections, source="reading_writing", path=db) == 2

    rows = sqlite3.connect(db).execute("SELECT category, source FROM mistakes").fetchall()
    assert rows == [("article", "reading_writing"), ("tense", "reading_writing")]


def test_reading_queue_round_trip(tmp_path):
    from app.db import pop_reading, queue_reading, reading_queue_size
    from app.schemas import ReadingText

    db = tmp_path / "test.db"
    passage = ReadingText(title="T", text="word " * 250)
    assert pop_reading(path=db) is None
    queue_reading("football", passage, path=db)
    assert reading_queue_size(path=db) == 1

    topic, popped = pop_reading(path=db)
    assert topic == "football" and popped.title == "T"
    assert reading_queue_size(path=db) == 0


def test_pick_topic_excludes_today():
    from app.topics import pick_topic

    assert all(pick_topic(exclude="football") != "football" for _ in range(50))
