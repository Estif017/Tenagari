"""Tests for the rule-based category check (no LLM needed)."""

import pytest

from app.categories import rule_category
from app.schemas import Correction


@pytest.mark.parametrize(("original", "corrected", "expected"), [
    ("married with a doctor", "married a doctor", "preposition"),      # extra
    ("discussed about the plan", "discussed the plan", "preposition"),
    ("interested about AI", "interested in AI", "preposition"),        # wrong
    ("I went to store", "I went to the store", "article"),             # missing
    ("The life in America", "Life in America", "article"),             # extra
    ("bought yesterday a laptop", "bought a laptop yesterday", "word_order"),
    ("I go to the office", "I went to the office", None),              # verb change: model decides
    ("he said me", "he told me", None),
    ("come with an idea", "come up with an idea", None),               # particle, not a preposition
    ("Same text.", "same text", None),                                 # no real change
])
def test_rule_category(original, corrected, expected):
    assert rule_category(original, corrected) == expected


def test_rule_overrides_model_label():
    c = Correction(original="married with", corrected="married", category="word_order", reason="r")
    assert c.category == "preposition"


def test_model_label_kept_when_rule_unsure():
    c = Correction(original="I go", corrected="I went", category="tense", reason="r")
    assert c.category == "tense"
