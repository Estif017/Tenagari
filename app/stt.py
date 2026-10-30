"""Speech-to-text with faster-whisper (runs locally on the CPU)."""

from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel

from app.config import load_config


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    """Load the Whisper model once (first run downloads it, ~150 MB for base.en)."""
    # int8 = smaller and faster on CPU with almost no accuracy loss
    return WhisperModel(load_config()["stt"]["model"], device="cpu", compute_type="int8")


def transcribe(path: Path) -> str:
    """Return the text spoken in an audio file."""
    segments, _info = get_model().transcribe(
        str(path),
        language="en",
        beam_size=5,
        vad_filter=True,                   # skip silence (pauses while thinking)
        condition_on_previous_text=False,  # fewer hallucinated repeats
    )
    return " ".join(s.text.strip() for s in segments).strip()
