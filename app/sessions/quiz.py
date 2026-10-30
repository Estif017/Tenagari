"""Grammar quiz: 5 questions targeting his top mistake categories."""

import random
import subprocess
import sys
from difflib import SequenceMatcher
from itertools import cycle

from app.db import (pop_quiz, queue_quiz, quiz_queue_size, recent_mistakes, save_quiz_result,
                    top_mistake_categories)
from app.llm import LLMError, ask_json
from app.prompts import CATEGORY_GUIDE
from app.categories import has_typo, rule_category
from app.config import ROOT
from app.schemas import (QUIZ_DRAFTS, QUIZ_SIZE, AnswerCheck, CheckedItem, ItemChecks, QuizItem, QuizItems, QuizQuestion,
                         normalize_text)

# Common trouble spots for Amharic speakers, used until the mistake log has data.
DEFAULT_CATEGORIES = ["article", "tense", "preposition"]
QUIZZABLE = {"article", "tense", "word_order", "preposition", "word_choice"}  # text-only, so no pronunciation
SHARES = [3, 2, 2]  # drafts per category (sums to QUIZ_DRAFTS), biggest weakness first


def pick_categories() -> list[str]:
    """Top 3 quizzable categories from the last 14 days, padded with defaults."""
    top = [c for c, _ in top_mistake_categories(days=14, limit=7) if c in QUIZZABLE][:3]
    for c in DEFAULT_CATEGORIES:
        if len(top) == 3:
            break
        if c not in top:
            top.append(c)
    return top


def generate_items(categories: list[str]) -> list[QuizItem]:
    """Ask the model for 5 (correct, wrong, wrong2) sentence sets, inspired by his real mistakes.

    The model only writes sentences; code turns them into questions, so the
    question format and answer key can't come out inconsistent.
    """
    plan = []
    for category, n in zip(categories, SHARES):
        examples = "; ".join(f'"{m["original"]}" → "{m["corrected"]}"' for m in recent_mistakes(category, 3))
        plan.append(f"- {n} item(s) on {category}" + (f" (mistakes he made: {examples})" if examples else ""))
    prompt = (
        f"Write {QUIZ_DRAFTS} grammar practice items for an upper-intermediate (B2) English learner.\n"
        + "\n".join(plan) + "\n\n"
        "Each item:\n"
        "- correct: a natural, fully correct sentence.\n"
        "- wrong: the SAME sentence with exactly ONE typical learner mistake of that category "
        "(change only 1-3 words).\n"
        "- wrong2: the SAME sentence with a DIFFERENT mistake of that category.\n"
        "- rule: the grammar rule in one short sentence. Make sure it is true.\n"
        "The mistakes must be real grammar or word-choice mistakes, never spelling typos. "
        "Only ONE of the three sentences may be correct English.\n\n"
        "Write NEW sentences that test the same rules as his mistakes; do not reuse his sentences. "
        "Use a different situation for each item (work, home, travel, friends, shopping...).\n\n"
        + CATEGORY_GUIDE
    )
    return ask_json(prompt, QuizItems, temperature=0.8, task="generate").items


MAX_ROUNDS = 3  # draft+check rounds before giving up on reaching QUIZ_SIZE
LOG_DIR = ROOT / "data" / "logs"


def check_items(items: list[QuizItem]) -> list[CheckedItem]:
    """Have the feedback model verify each draft; keep usable ones with its rule and category."""
    listing = "\n".join(
        f"{i}. correct: {it.correct}\n   wrong: {it.wrong}\n   wrong2: {it.wrong2}" for i, it in enumerate(items)
    )
    prompt = (
        "Check these grammar quiz items for an English learner. For EACH item (by index):\n"
        "- correct_is_correct: is 'correct' fully correct, natural English?\n"
        "- wrong_has_mistake / wrong2_has_mistake: does it contain a real grammar or word-choice mistake? "
        "If the sentence is also acceptable English (even if less common), answer false. Typos alone: false.\n"
        "- category: the category of the mistake in 'wrong'.\n"
        "- rule: the true rule that 'wrong' breaks, in one short sentence.\n\n"
        f"{listing}\n\n{CATEGORY_GUIDE}"
    )
    checks = {c.index: c for c in ask_json(prompt, ItemChecks, task="feedback").checks}
    good = []
    for i, item in enumerate(items):
        check = checks.get(i)
        if has_typo(item.correct, item.wrong):  # checker sometimes passes typos; the dictionary doesn't
            continue
        if check and check.usable:
            good.append(CheckedItem(
                category=rule_category(item.wrong, item.correct) or check.category,
                correct=item.correct,
                wrong=item.wrong,
                wrong2=item.wrong2 if check.wrong2_has_mistake and not has_typo(item.correct, item.wrong2) else None,
                rule=check.rule,
            ))
    return good


def blank_out(correct: str, wrong: str) -> tuple[str, str] | None:
    """Turn a sentence pair into (sentence with ___, missing words), if the fix is one small span.

    Returns None when the fix only deletes words (e.g. "married with" → "married"),
    since there's nothing to put in a blank.
    """
    tokens, wrong_tokens = correct.split(), wrong.split()
    ops = [op for op in SequenceMatcher(a=[normalize_text(t) for t in wrong_tokens],
                                        b=[normalize_text(t) for t in tokens]).get_opcodes() if op[0] != "equal"]
    if len(ops) != 1:
        return None
    _, i1, i2, j1, j2 = ops[0]
    if not 1 <= j2 - j1 <= 3:
        return None
    answer = normalize_text(" ".join(tokens[j1:j2]))
    trailing = tokens[j2 - 1][len(tokens[j2 - 1].rstrip(".,!?;:")):]  # keep the sentence's final punctuation
    prompt = " ".join(tokens[:j1] + ["___" + trailing] + tokens[j2:])
    # Hint with the wrong word(s) so "Yesterday I ___ (go)" asks for "went", not "drove"
    hint = normalize_text(" ".join(wrong_tokens[i1:i2]))
    return (f"{prompt}  ({hint})" if hint else prompt), answer


def build_questions(items: list[CheckedItem], rng: random.Random | None = None) -> list[QuizQuestion]:
    """Turn sentence sets into a mix of question kinds (one fill_blank if any item allows it)."""
    rng = rng or random.Random()
    fill_index = next((i for i, item in enumerate(items) if blank_out(item.correct, item.wrong)), None)
    questions, alternate = [], cycle(["choose_correct", "fix_sentence"])
    for i, item in enumerate(items):
        if i == fill_index:
            prompt, answer = blank_out(item.correct, item.wrong)
            questions.append(QuizQuestion(kind="fill_blank", category=item.category, prompt=prompt,
                                          answer=answer, explanation=item.rule))
        elif item.wrong2 and next(alternate) == "choose_correct":
            options = [item.correct, item.wrong, item.wrong2]
            rng.shuffle(options)
            questions.append(QuizQuestion(kind="choose_correct", category=item.category,
                                          prompt="Which sentence is correct?", options=options,
                                          answer=item.correct, explanation=item.rule))
        else:
            questions.append(QuizQuestion(kind="fix_sentence", category=item.category, prompt=item.wrong,
                                          answer=item.correct, explanation=item.rule))
    return questions


def judge_free_answer(q: QuizQuestion, user_answer: str) -> AnswerCheck:
    """Ask the feedback model whether a non-matching free-text answer is still correct."""
    prompt = (
        f"Quiz question ({q.kind}): {q.prompt}\nExpected answer: {q.answer}\n"
        f"Student's answer: {user_answer}\n\n"
        "Is the student's answer also correct English that fixes the mistake / fills the blank properly? "
        "Small punctuation or capitalization differences are fine. Other new mistakes are not. "
        'Return JSON with "correct" (true/false) and "note" (one short, kind sentence).'
    )
    return ask_json(prompt, AnswerCheck, task="feedback")


def ask_question(i: int, q: QuizQuestion) -> tuple[str, str]:
    """Show one question; return (user answer as text, the correct answer as text)."""
    label = {"choose_correct": "Choose the correct sentence", "fill_blank": "Fill in the blank",
             "fix_sentence": "Fix the mistake"}[q.kind]
    print(f"\nQ{i} · {label}  [{q.category}]")
    print(f"  {q.prompt}")
    if q.kind == "choose_correct":
        for n, option in enumerate(q.options, 1):
            print(f"   {n}. {option}")
        while True:
            choice = input("Your choice (number): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(q.options):
                return q.options[int(choice) - 1], q.answer
            print(f"  Type a number from 1 to {len(q.options)}.")
    return input("Your answer: ").strip(), q.answer


def grade(q: QuizQuestion, user_answer: str) -> tuple[bool, str]:
    """Return (is_correct, note). Exact match first; the LLM judges only free-text mismatches."""
    if normalize_text(user_answer) == normalize_text(q.answer):
        return True, ""
    if q.kind == "choose_correct" or not user_answer:
        return False, ""
    check = judge_free_answer(q, user_answer)
    return check.correct, check.note


def make_items() -> list[CheckedItem]:
    """Draft and verify items for his current top categories, topping up until QUIZ_SIZE."""
    categories = pick_categories()
    kept: dict[str, CheckedItem] = {}  # keyed by sentence, so rounds don't repeat questions
    for round_no in range(1, MAX_ROUNDS + 1):
        print(f"Writing questions on {', '.join(categories)} (round {round_no})...")
        try:
            drafts = generate_items(categories)
            print("Double-checking the answers...")
            checked = check_items(drafts)
        except LLMError as e:  # one bad round shouldn't sink the quiz; try another
            print(f"  Round {round_no} failed ({str(e)[:80]}...). Trying again.")
            continue
        for item in checked:
            kept.setdefault(normalize_text(item.correct), item)
        if len(kept) >= QUIZ_SIZE:
            break
    return list(kept.values())[:QUIZ_SIZE]


def get_todays_items() -> list[CheckedItem]:
    """Use a pre-generated quiz if one is queued; otherwise make one now."""
    queued = pop_quiz()
    if queued:
        print("Grammar quiz (prepared yesterday)")
        return queued
    return make_items()


def prepare_next_quiz() -> None:
    """Pre-generate the next quiz if the queue is empty (uses today's mistakes too).

    Run by `python -m app.main prepare-quiz`, usually in the background.
    """
    if quiz_queue_size() > 0:
        print("A quiz is already queued.")
        return
    items = make_items()
    if items:
        queue_quiz(items)
        print(f"Ready: {len(items)} questions queued.")


def prepare_next_quiz_in_background() -> None:
    """Start prepare-quiz as a separate process so he doesn't wait (it takes a few minutes)."""
    if quiz_queue_size() > 0:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = (LOG_DIR / "prepare_quiz.log").open("a")
    subprocess.Popen(
        [sys.executable, "-m", "app.main", "prepare-quiz"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True,  # keeps running after this command exits
    )
    print("\nPreparing tomorrow's quiz in the background (log: data/logs/prepare_quiz.log).")


def run() -> None:
    """Run the quiz end to end and log every answer."""
    questions = build_questions(get_todays_items())
    if not questions:
        print("Sorry, none of today's questions passed the check. Try again: python -m app.main quiz")
        return

    score = 0
    for i, q in enumerate(questions, 1):
        user_answer, correct_answer = ask_question(i, q)
        is_correct, note = grade(q, user_answer)
        score += is_correct
        if is_correct:
            print("  ✅ Correct!" + (f" {note}" if note else ""))
        else:
            print(f"  ❌ Answer: {correct_answer}" + (f"\n     {note}" if note else ""))
        print(f"     Rule: {q.explanation}")
        save_quiz_result(q.category, q.kind, q.prompt, user_answer, correct_answer, is_correct)

    total = len(questions)
    print(f"\n=== Score: {score}/{total} ===")
    if score == total:
        print("Excellent! Perfect score.")
    elif score >= total * 0.6:
        print("Nice work. These rules get easier every time you see them.")
    else:
        print("Good practice. Mistakes here are how the rules stick.")

    prepare_next_quiz_in_background()
