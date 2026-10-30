"""Tests for the feedback schema and saving mistakes (no LLM needed)."""

import sqlite3

from app.db import save_mistakes
from app.schemas import Correction, WritingFeedback


def make_correction(category: str = "article") -> dict:
    return {"original": "I went to store", "corrected": "I went to the store",
            "category": category, "reason": "Use 'the' for a specific place."}


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
