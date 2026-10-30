"""Tests for the grammar quiz (no LLM needed)."""

import random
import sqlite3

import pytest
from pydantic import ValidationError

from app.db import save_quiz_result
from app.schemas import AnswerCheck, CheckedItem, QuizItem, QuizItems, QuizQuestion
from app.sessions import quiz


def question(**overrides) -> dict:
    q = {"kind": "fix_sentence", "category": "preposition", "prompt": "She married with a doctor.",
         "options": [], "answer": "She married a doctor.", "explanation": "'marry' takes no preposition."}
    return q | overrides


def item(n: int = 0, **overrides) -> dict:
    i = {"category": "tense", "correct": f"Yesterday I went to the gym {n} times.",
         "wrong": f"Yesterday I go to the gym {n} times.", "wrong2": f"Yesterday I going to the gym {n} times.",
         "rule": "Use the past simple for finished past actions."}
    return i | overrides


def checked(n: int = 0, **overrides) -> CheckedItem:
    return CheckedItem(**(item(n) | overrides))


def test_item_rejects_identical_or_rewritten_sentences():
    with pytest.raises(ValidationError, match="all be different"):
        QuizItem(**item(wrong="Yesterday I went to the gym 0 times"))  # same as correct, minus the period
    with pytest.raises(ValidationError, match="changes too much"):
        QuizItem(**item(wrong2="My brother never likes going to any gym on weekends."))


def test_items_drop_bad_drafts_instead_of_failing():
    bad = item(9, wrong2="My brother never likes going to any gym on weekends.")
    items = QuizItems(items=[item(0), bad, item(1), item(1), item(2)]).items  # 1 invalid, 1 duplicate
    assert [i.correct for i in items] == [item(n)["correct"] for n in range(3)]
    with pytest.raises(ValidationError, match="only 2 usable"):
        QuizItems(items=[item(0), item(1), bad])
    assert len(QuizItems(items=[item(n) for n in range(9)]).items) == 7  # QUIZ_DRAFTS


def test_reordered_words_count_as_one_small_change():
    QuizItem(**item(correct="I always go to the gym in the morning.",
                    wrong="I always go in the morning to the gym.",
                    wrong2="I go always to the gym in the morning."))  # no error


def test_make_items_survives_a_failed_round(monkeypatch):
    from app.llm import LLMError

    results = iter([LLMError("bad json"), [checked(n) for n in range(5)]])
    def fake_check(drafts):
        r = next(results)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(quiz, "generate_items", lambda cats: [])
    monkeypatch.setattr(quiz, "check_items", fake_check)
    monkeypatch.setattr(quiz, "pick_categories", lambda: ["tense"])
    assert len(quiz.make_items()) == 5


@pytest.mark.parametrize(("correct", "wrong", "expected"), [
    ("Yesterday I went to the gym.", "Yesterday I go to the gym.", ("Yesterday I ___ to the gym.  (go)", "went")),
    ("I went to the store.", "I went to store.", ("I went to ___ store.", "the")),
    ("I am interested in AI.", "I am interested about AI.", ("I am interested ___ AI.  (about)", "in")),
    ("I finished it today.", "I finished it todays.", ("I finished it ___.  (todays)", "today")),  # keeps the period
    ("She married a doctor.", "She married with a doctor.", None),  # deletion only: nothing to fill in
])
def test_blank_out(correct, wrong, expected):
    assert quiz.blank_out(correct, wrong) == expected


def test_build_questions_skips_choose_correct_without_wrong2():
    questions = quiz.build_questions([checked(n, wrong2=None) for n in range(4)])
    assert "choose_correct" not in [q.kind for q in questions]


def test_build_questions_mixes_kinds_and_keys_match():
    items = [checked(n) for n in range(5)]
    questions = quiz.build_questions(items, rng=random.Random(0))
    assert [q.kind for q in questions] == ["fill_blank", "choose_correct", "fix_sentence",
                                           "choose_correct", "fix_sentence"]
    for q, it in zip(questions, items):
        if q.kind == "choose_correct":
            assert q.answer == it.correct and sorted(q.options) == sorted([it.correct, it.wrong, it.wrong2])
        elif q.kind == "fix_sentence":
            assert (q.prompt, q.answer) == (it.wrong, it.correct)


def test_pick_categories_pads_with_defaults(monkeypatch):
    monkeypatch.setattr(quiz, "top_mistake_categories", lambda **kw: [("word_choice", 4), ("pronunciation", 2)])
    assert quiz.pick_categories() == ["word_choice", "article", "tense"]  # pronunciation skipped


def test_grade_exact_match_skips_llm(monkeypatch):
    monkeypatch.setattr(quiz, "judge_free_answer", lambda q, a: pytest.fail("LLM should not be called"))
    assert quiz.grade(QuizQuestion(**question()), "she married a doctor") == (True, "")


def test_grade_asks_llm_for_other_free_answers(monkeypatch):
    monkeypatch.setattr(quiz, "judge_free_answer", lambda q, a: AnswerCheck(correct=True, note="Also right!"))
    assert quiz.grade(QuizQuestion(**question()), "She got married to a doctor.") == (True, "Also right!")


def test_save_quiz_result(tmp_path):
    db = tmp_path / "t.db"
    save_quiz_result("tense", "fill_blank", "I ___ there.", "go", "went", False, path=db)
    row = sqlite3.connect(db).execute("SELECT category, is_correct FROM quiz_results").fetchone()
    assert row == ("tense", 0)


def test_check_items_keeps_only_verified_and_uses_checker_rule(monkeypatch):
    from app.schemas import ItemCheck, ItemChecks

    items = [QuizItem(**item(n)) for n in range(4)]
    items[2] = QuizItem(**item(2, category="tense", correct="I went to the store 2 times.",
                               wrong="I went to store 2 times.", wrong2="I went to a stores 2 times."))
    verdicts = ItemChecks(checks=[
        ItemCheck(index=0, correct_is_correct=True, wrong_has_mistake=True, wrong2_has_mistake=True,
                  category="tense", rule="Past simple for finished actions."),
        ItemCheck(index=1, correct_is_correct=True, wrong_has_mistake=False, wrong2_has_mistake=True,
                  category="tense", rule="x"),  # 'wrong' is acceptable English -> dropped
        ItemCheck(index=3, correct_is_correct=True, wrong_has_mistake=True, wrong2_has_mistake=False,
                  category="tense", rule="y"),  # only wrong2 is fine English -> kept, wrong2 dropped
        ItemCheck(index=2, correct_is_correct=True, wrong_has_mistake=True, wrong2_has_mistake=True,
                  category="tense", rule="Use 'the' for a specific place."),
    ])
    monkeypatch.setattr(quiz, "ask_json", lambda *a, **kw: verdicts)
    kept = quiz.check_items(items)
    assert [k.correct for k in kept] == [items[0].correct, items[2].correct, items[3].correct]
    assert kept[2].wrong2 is None
    assert kept[0].rule == "Past simple for finished actions."
    assert kept[1].category == "article"  # diff rule overrides the label


def test_quiz_queue_round_trip(tmp_path):
    from app.db import pop_quiz, queue_quiz, quiz_queue_size

    db = tmp_path / "t.db"
    items = [checked(n) for n in range(2)] + [checked(2, wrong2=None)]
    assert pop_quiz(path=db) is None
    queue_quiz(items, path=db)
    assert quiz_queue_size(path=db) == 1
    assert pop_quiz(path=db) == items
    assert quiz_queue_size(path=db) == 0


def test_run_uses_queue_then_prepares_next_in_background(monkeypatch):
    """A queued quiz starts with no generation; tomorrow's is prepared in the background."""
    calls = []
    monkeypatch.setattr(quiz, "pop_quiz", lambda: [checked(n) for n in range(3)])
    monkeypatch.setattr(quiz, "make_items", lambda: pytest.fail("should use the queued quiz"))
    monkeypatch.setattr(quiz, "prepare_next_quiz_in_background", lambda: calls.append("prepare"))
    monkeypatch.setattr(quiz, "save_quiz_result", lambda *a: None)
    monkeypatch.setattr("builtins.input", lambda *a: "1")
    monkeypatch.setattr(quiz, "judge_free_answer", lambda q, a: AnswerCheck(correct=False, note=""))
    quiz.run()
    assert calls == ["prepare"]


def test_prepare_next_quiz_queues_only_when_empty(monkeypatch):
    queued = []
    monkeypatch.setattr(quiz, "make_items", lambda: [checked(0)])
    monkeypatch.setattr(quiz, "queue_quiz", queued.append)
    monkeypatch.setattr(quiz, "quiz_queue_size", lambda: 1)
    quiz.prepare_next_quiz()
    assert queued == []
    monkeypatch.setattr(quiz, "quiz_queue_size", lambda: 0)
    quiz.prepare_next_quiz()
    assert queued == [[checked(0)]]


def test_make_items_tops_up_across_rounds(monkeypatch):
    rounds = iter([[checked(0), checked(1)], [checked(1), checked(2), checked(3)], [checked(4), checked(5)]])
    monkeypatch.setattr(quiz, "generate_items", lambda cats: [])
    monkeypatch.setattr(quiz, "check_items", lambda drafts: next(rounds))
    monkeypatch.setattr(quiz, "pick_categories", lambda: ["tense"])
    items = quiz.make_items()
    assert [i.correct for i in items] == [checked(n).correct for n in range(5)]  # dedup, then stop at 5


def test_background_prepare_is_blocked_in_tests():
    """Proves conftest's guard works: tests can't launch a real prepare-quiz process."""
    with pytest.raises(AssertionError, match="tried to start a process"):
        quiz.prepare_next_quiz_in_background()
