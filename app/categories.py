"""Rule-based category check: when the word diff makes the category certain, trust it over the LLM.

Small models mislabel some fixes, e.g. "married with → married" as word_order.
If a fix only adds/removes/swaps articles, it's an article fix; only prepositions,
a preposition fix; the same words reordered, a word_order fix. Otherwise we keep
the model's label.
"""

import re
from difflib import SequenceMatcher

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
