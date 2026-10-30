"""Tests for the mistake stats and word bank (no LLM needed)."""

import sqlite3
from datetime import date, timedelta

from app.db import (add_word, list_words, practice_words, record_correct_use, save_mistakes,
                    top_mistake_categories)
from app.schemas import Correction
from app.word_bank import find_used_words


def correction(category: str) -> Correction:
    return Correction(original="x", corrected="y", category=category, reason="r")


def test_find_used_words_handles_inflections_and_phrases():
    transcript = "We came up with a plan and mitigated the risk. Then I applied for the job."
    bank = ["mitigate", "apply", "come up with", "deadline"]
    # "came" doesn't match "come": irregular forms are a known limit
    assert find_used_words(transcript, bank) == ["mitigate", "apply"]
    assert find_used_words("I will come up with ideas", ["come up with"]) == ["come up with"]


def test_find_used_words_needs_whole_word():
    assert find_used_words("we start at nine", ["art"]) == []  # no match inside another word


def test_top_categories_counts_recent_only(tmp_path):
    db = tmp_path / "t.db"
    save_mistakes([correction("tense")] * 3 + [correction("article")], source="speaking", path=db)
    old = (date.today() - timedelta(days=30)).isoformat()
    with sqlite3.connect(db) as conn:  # an old mistake that should not count
        conn.execute("INSERT INTO mistakes (date, source, category, original, corrected) "
                     "VALUES (?, 'speaking', 'preposition', 'a', 'b')", (old,))
    assert top_mistake_categories(days=7, path=db) == [("tense", 3), ("article", 1)]


def test_word_lifecycle(tmp_path):
    db = tmp_path / "t.db"
    assert add_word("come up with", "We came up with a plan.", path=db)
    assert not add_word("Come Up With", path=db)  # duplicates ignored, any case
    assert [w["word"] for w in practice_words(2, path=db)] == ["come up with"]

    assert record_correct_use("come up with", path=db) is False
    assert record_correct_use("come up with", path=db) is False
    assert record_correct_use("come up with", path=db) is True  # 3rd use retires it
    assert list_words(path=db) == []
    assert practice_words(2, path=db) == []
    assert len(list_words(include_retired=True, path=db)) == 1


def test_word_in_a_correction_gets_no_credit(tmp_path, monkeypatch, capsys):
    from app.schemas import SpeakingFeedback, WordUse
    from app.sessions import speaking

    credited = []
    monkeypatch.setattr(speaking, "record_correct_use", lambda w: credited.append(w) or False)
    fb = SpeakingFeedback(
        corrections=[Correction(original="We discussed about it", corrected="We discussed it",
                                category="preposition", reason="r")],
        encouragement="Nice!",
        word_usage=[WordUse(word="discuss", used_correctly=True, note="ok"),
                    WordUse(word="deadline", used_correctly=True, note="ok")],
    )
    speaking.update_word_bank(fb, ["discuss", "deadline"])
    assert credited == ["deadline"]
    assert "close!" in capsys.readouterr().out
