"""Pydantic models describing every JSON shape we expect from the LLM."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

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


class WritingFeedback(BaseModel):
    """Tutor feedback on a written summary."""

    summary_score: int = Field(ge=0, le=10, description="How well the summary captures the main idea, 0-10")
    corrections: list[Correction] = Field(default_factory=list, description="At most 3, most important first")
    better_phrases: list[str] = Field(default_factory=list, description="Natural phrases the learner could use")
    encouragement: str

    @field_validator("corrections")
    @classmethod
    def keep_top_three(cls, value: list[Correction]) -> list[Correction]:
        """Never overwhelm the learner: keep only the first 3 corrections."""
        return value[:MAX_CORRECTIONS]
