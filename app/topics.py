"""Topic picker. RSS-based topics come later (Step 10)."""

import random

from app.config import load_config


def pick_topic(rng: random.Random | None = None) -> str:
    """Return a random topic from config.yaml."""
    return (rng or random).choice(load_config()["topics"])
