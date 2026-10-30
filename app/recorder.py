"""Microphone recording: record until Enter, save as a WAV file."""

import wave
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

from app.config import ROOT

RECORDINGS_DIR = ROOT / "data" / "recordings"


def new_recording_path(kind: str) -> Path:
    """Return a dated path like data/recordings/2026-10-29/speaking_091502.wav."""
    now = datetime.now()
    folder = RECORDINGS_DIR / now.date().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{kind}_{now:%H%M%S}.wav"


def save_wav(audio: np.ndarray, samplerate: int, path: Path) -> None:
    """Write mono int16 samples to a WAV file (stdlib `wave`, no extra deps)."""
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)  # int16 = 2 bytes
        f.setframerate(samplerate)
        f.writeframes(audio.astype(np.int16).tobytes())


def record_until_enter(path: Path) -> float:
    """Record from the default mic until the user presses Enter. Returns seconds recorded."""
    samplerate = int(sd.query_devices(kind="input")["default_samplerate"])
    chunks: list[np.ndarray] = []

    def on_audio(indata: np.ndarray, frames: int, time_info, status) -> None:
        chunks.append(indata.copy())  # runs on the audio thread for every block

    with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", callback=on_audio):
        input("🎙  Recording... take your time. Press Enter when you're done.")

    audio = np.concatenate(chunks) if chunks else np.zeros((0, 1), dtype=np.int16)
    save_wav(audio, samplerate, path)
    return len(audio) / samplerate
