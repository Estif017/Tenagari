"""Word bank logic: spotting bank words in a transcript, adding words with examples."""

import re

from app.db import add_word
from app.llm import LLMError, ask_json
from app.schemas import WordInfo


def _stem(word: str) -> str:
    """Rough stem so 'mitigate' also matches 'mitigated'/'mitigating', 'apply' matches 'applied'."""
    word = word.lower()
    if len(word) > 3 and word[-1] in "ey":
        return word[:-1]
    return word


def word_pattern(entry: str) -> re.Pattern[str]:
    """Regex for a word or phrase, allowing inflected endings on each word."""
    parts = [re.escape(_stem(w)) + r"\w*" for w in entry.split()]
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)


def find_used_words(transcript: str, entries: list[str]) -> list[str]:
    """Return the bank entries that appear (in some form) in the transcript."""
    return [e for e in entries if word_pattern(e).search(transcript)]


def add_with_example(word: str, example: str | None = None) -> tuple[bool, WordInfo | None]:
    """Add a word; if no example is given, ask the fast model for a meaning + example.

    Returns (was_added, info). If Ollama is unavailable, the word is saved without an example.
    """
    info = None
    if example is None:
        try:
            info = ask_json(
                f'Explain the English word or phrase "{word}" for an upper-intermediate learner. '
                'Return JSON with "meaning" (one short sentence) and "example" '
                "(one natural everyday sentence using it).",
                WordInfo,
                task="generate",
            )
            example = info.example
        except LLMError:
            pass
    return add_word(word, example), info
