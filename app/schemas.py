"""Pydantic models describing every JSON shape we expect from the LLM."""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.categories import changed_word_count, rule_category

Category = Literal["article", "tense", "word_order", "preposition", "word_choice", "pronunciation", "other"]
CATEGORIES: tuple[str, ...] = Category.__args__
MAX_CORRECTIONS = 3


class HelloResponse(BaseModel):
    """Smoke-test response used by `python -m app.main hello`."""

    greeting: str
    language: str


MIN_READING_WORDS = 200


class ReadingText(BaseModel):
    """A generated reading passage."""

    title: str
    text: str

    @field_validator("text")
    @classmethod
    def long_enough(cls, value: str) -> str:
        """Small models often write too little; failing here triggers a retry."""
        words = len(value.split())
        if words < MIN_READING_WORDS:
            raise ValueError(f"text has only {words} words; write 250-400 words")
        return value


class Correction(BaseModel):
    """One fix: what the learner wrote/said, the better version, and why."""

    original: str
    corrected: str
    category: Category
    reason: str

    @field_validator("category", mode="before")
    @classmethod
    def unknown_to_other(cls, value: Any) -> str:
        """Map labels the model invents (e.g. 'grammar') to 'other' instead of failing."""
        value = str(value).strip().lower().replace(" ", "_")
        return value if value in CATEGORIES else "other"

    @model_validator(mode="after")
    def fix_category_from_diff(self) -> "Correction":
        """Override the model's label when the word diff makes the category certain."""
        self.category = rule_category(self.original, self.corrected) or self.category
        return self


class Feedback(BaseModel):
    """Tutor feedback on something the learner wrote or said."""

    corrections: list[Correction] = Field(default_factory=list, description="At most 3, most important first")
    better_phrases: list[str] = Field(default_factory=list, description="Natural phrases the learner could use")
    encouragement: str

    @field_validator("corrections")
    @classmethod
    def keep_top_three(cls, value: list[Correction]) -> list[Correction]:
        """Never overwhelm the learner: keep only the first 3 corrections."""
        return value[:MAX_CORRECTIONS]


class WritingFeedback(Feedback):
    """Feedback on a written summary, plus how well it captured the main idea."""

    summary_score: int = Field(ge=0, le=10, description="How well the summary captures the main idea, 0-10")


class SpeakingQuestion(BaseModel):
    """A daily speaking prompt."""

    question: str
    starter_phrase: str = Field(description="A natural time-buying phrase to start the answer")


class WordUse(BaseModel):
    """Whether a word-bank entry was used correctly in an answer."""

    word: str
    used_correctly: bool
    note: str = Field(description="One short sentence: why it was right, or how to use it better")


class SpeakingFeedback(Feedback):
    """Feedback on a spoken answer, plus checks on the word-bank words he tried."""

    word_usage: list[WordUse] = Field(default_factory=list)


QUIZ_SIZE = 5
QuizKind = Literal["choose_correct", "fill_blank", "fix_sentence"]
QUIZ_KINDS: tuple[str, ...] = QuizKind.__args__


def normalize_text(text: str) -> str:
    """Lowercase, drop punctuation and extra spaces, for forgiving comparisons."""
    return " ".join(re.sub(r"[^\w\s']", " ", text.lower()).split())


MAX_CHANGED_WORDS = 4  # a quiz mistake should be one small change, not a rewrite


class QuizItem(BaseModel):
    """What the LLM writes: one correct sentence and two wrong versions. Code builds the question."""

    category: Category
    correct: str = Field(description="A natural, fully correct sentence (8-16 words)")
    wrong: str = Field(description="The SAME sentence with ONE typical learner mistake of this category")
    wrong2: str = Field(description="The SAME sentence with a DIFFERENT mistake of this category")
    rule: str = Field(description="The grammar rule in one short, true sentence")

    @model_validator(mode="after")
    def one_small_change(self) -> "QuizItem":
        """Each wrong version must differ from the correct one, by a small change."""
        if len({normalize_text(s) for s in (self.correct, self.wrong, self.wrong2)}) < 3:
            raise ValueError(f"'{self.correct}': correct, wrong and wrong2 must all be different")
        for wrong in (self.wrong, self.wrong2):
            is_reorder = rule_category(wrong, self.correct) == "word_order"  # moved words are one mistake
            if not is_reorder and changed_word_count(self.correct, wrong) > MAX_CHANGED_WORDS:
                raise ValueError(f"'{wrong}' changes too much: change only 1-3 words of the correct sentence")
        return self


QUIZ_DRAFTS = QUIZ_SIZE + 2  # write extra items, since the checker may reject some
MIN_USABLE_DRAFTS = 3       # fewer than this and we retry; quiz.make_items tops up across rounds


class QuizItems(BaseModel):
    items: list[QuizItem]

    @field_validator("items", mode="before")
    @classmethod
    def drop_bad_drafts(cls, value: Any) -> Any:
        """Drop invalid or duplicate drafts one by one instead of failing the whole batch."""
        if not isinstance(value, list):
            return value  # let pydantic report the type error
        kept, seen = [], set()
        for raw in value:
            try:
                item = QuizItem.model_validate(raw)
            except ValidationError:
                continue
            key = normalize_text(item.correct)
            if key not in seen:
                seen.add(key)
                kept.append(item)
        if len(kept) < MIN_USABLE_DRAFTS:
            raise ValueError(f"only {len(kept)} usable items; each wrong sentence must be the SAME sentence "
                             "with only 1-3 words changed, and every item needs a different sentence")
        return kept[:QUIZ_DRAFTS]


class ItemCheck(BaseModel):
    """The feedback model's verdict on one drafted quiz item."""

    index: int
    correct_is_correct: bool = Field(description="Is 'correct' fully correct, natural English?")
    wrong_has_mistake: bool = Field(description="Does 'wrong' contain a real grammar/word mistake (not just a typo)?")
    wrong2_has_mistake: bool = Field(description="Does 'wrong2' contain a real grammar/word mistake (not just a typo)?")
    category: Category = Field(description="The category of the mistake in 'wrong'")
    rule: str = Field(description="The true grammar rule that 'wrong' breaks, in one short sentence")

    @property
    def usable(self) -> bool:
        """Good enough for fix_sentence/fill_blank; choose_correct also needs wrong2."""
        return self.correct_is_correct and self.wrong_has_mistake


class ItemChecks(BaseModel):
    checks: list[ItemCheck]


class CheckedItem(BaseModel):
    """A verified quiz item. wrong2 is None if the checker found it acceptable English."""

    category: Category
    correct: str
    wrong: str
    wrong2: str | None
    rule: str


class QuizQuestion(BaseModel):
    """A question shown to the learner, built by code from a QuizItem."""

    kind: QuizKind
    category: Category
    prompt: str
    options: list[str] = Field(default_factory=list)
    answer: str
    explanation: str


class AnswerCheck(BaseModel):
    """The tutor's verdict on a free-text quiz answer."""

    correct: bool
    note: str = Field(description="One short sentence")


class WordInfo(BaseModel):
    """Meaning and example for a new word-bank entry."""

    meaning: str
    example: str
