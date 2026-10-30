"""Rule-based category check: when the word diff makes the category certain, trust it over the LLM.

Small models mislabel some fixes, e.g. "married with → married" as word_order.
If a fix only adds/removes/swaps articles, it's an article fix; only prepositions,
a preposition fix; the same words reordered, a word_order fix. Otherwise we keep
the model's label.
"""

import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

ARTICLES = {"a", "an", "the"}
# Particles like up/out/off are left out on purpose ("come up with" is word choice).
PREPOSITIONS = {
    "about", "above", "across", "after", "against", "along", "among", "around", "at", "before",
    "behind", "below", "beside", "between", "by", "during", "for", "from", "in", "inside", "into",
    "near", "of", "on", "onto", "over", "since", "through", "to", "toward", "towards", "under",
    "until", "upon", "with", "within", "without",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def rule_category(original: str, corrected: str) -> str | None:
    """Return the certain category for this fix, or None if the diff is ambiguous."""
    old, new = _words(original), _words(corrected)
    if old == new:
        return None
    if sorted(old) == sorted(new):
        return "word_order"

    changed: set[str] = set()
    for op, i1, i2, j1, j2 in SequenceMatcher(a=old, b=new).get_opcodes():
        if op != "equal":
            changed.update(old[i1:i2], new[j1:j2])
    if changed <= ARTICLES:
        return "article"
    if changed <= PREPOSITIONS:
        return "preposition"
    return None


def changed_word_count(a: str, b: str) -> int:
    """How many words differ between two sentences (the longer side of each changed span)."""
    old, new = _words(a), _words(b)
    return sum(max(i2 - i1, j2 - j1)
               for op, i1, i2, j1, j2 in SequenceMatcher(a=old, b=new).get_opcodes() if op != "equal")


WORD_LIST = Path("/usr/share/dict/words")  # ships with macOS


@lru_cache(maxsize=1)
def _dictionary() -> frozenset[str]:
    """Known English words (empty if the word list is missing, which disables typo checks)."""
    if not WORD_LIST.exists():
        return frozenset()
    return frozenset(WORD_LIST.read_text().lower().split())


def _is_known(word: str) -> bool:
    """True if the word, or its stem without -s/-es/-ed/-ing, is in the dictionary."""
    words = _dictionary()
    candidates = {word, word.removesuffix("'s")}
    for suffix in ("s", "es", "ed", "d", "ing"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            candidates.add(word[: -len(suffix)])
    return any(c in words for c in candidates)


def has_typo(correct: str, wrong: str) -> bool:
    """True if the 'mistake' introduces a misspelled word (we want grammar mistakes, not typos)."""
    if not _dictionary():
        return False
    added = set(_words(wrong)) - set(_words(correct))
    return any(not _is_known(w) for w in added)
