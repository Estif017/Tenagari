"""Load settings from config.yaml at the project root."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    """Read config.yaml once and return it as a dict."""
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
