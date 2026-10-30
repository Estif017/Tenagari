"""Does the feedback model label known mistakes with the right category?

Calls the real model, so it's skipped by default. Run with: pytest -m llm -v
Sentences are deliberately different from the examples in prompts.CATEGORY_GUIDE,
so the test checks understanding, not copying.
"""

import ollama
import pytest

from app.llm import ask_json
from app.prompts import TUTOR_SYSTEM
from app.schemas import Feedback

pytestmark = pytest.mark.llm

# Each one sits on a boundary the model has confused before (e.g. an EXTRA word
# being labeled word_order instead of preposition/article).
KNOWN_MISTAKES = [
    ("She married with a doctor last year.", "preposition"),  # extra preposition
    ("I am living in Atlanta since 2020.", "tense"),          # present perfect, not "since"
    ("The life in America is very busy.", "article"),         # extra "the"
    ("I bought yesterday a new laptop.", "word_order"),       # adverb placement
    ("I make my homework every night.", "word_choice"),       # collocation: do homework
]


@pytest.fixture(scope="module", autouse=True)
def require_ollama():
    try:
        ollama.list()
    except Exception:
        pytest.skip("Ollama is not running")


@pytest.mark.parametrize(("sentence", "expected"), KNOWN_MISTAKES)
def test_category_label(sentence: str, expected: str):
    # TUTOR_SYSTEM (not tutor_system()) so the test doesn't depend on the mistake log
    fb = ask_json(
        f'Correct this sentence written by the student:\n"{sentence}"\n'
        "It contains exactly one mistake. Return one correction, plus better_phrases and encouragement.",
        Feedback,
        system=TUTOR_SYSTEM,
        task="feedback",
    )
    assert fb.corrections, "model found no mistake"
    got = fb.corrections[0]
    assert got.category == expected, f"{got.original!r} → {got.corrected!r} labeled {got.category}"
