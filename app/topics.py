"""Topic picker. RSS-based topics come later (Step 10)."""

import random

from app.config import load_config


def pick_topic(exclude: str | None = None, rng: random.Random | None = None) -> str:
    """Return a random topic from config.yaml, avoiding `exclude` when possible."""
    topics = [t for t in load_config()["topics"] if t != exclude] or load_config()["topics"]
    return (rng or random).choice(topics)
