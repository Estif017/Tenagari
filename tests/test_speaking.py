"""Tests for the speaking drill helpers (no mic, Whisper or LLM needed)."""

import sqlite3
import wave
from datetime import date, timedelta

import numpy as np

from app.db import save_recording
from app.recorder import save_wav
from app.sessions.speaking import THEMES, theme_for


def test_theme_rotates_daily():
    start = date(2026, 11, 1)
    themes = [theme_for(start + timedelta(days=i)) for i in range(len(THEMES))]
    assert sorted(themes) == sorted(THEMES)


def test_save_wav_round_trip(tmp_path):
    path = tmp_path / "a.wav"
    audio = (np.sin(np.linspace(0, 100, 24000)) * 10000).astype(np.int16).reshape(-1, 1)
    save_wav(audio, 24000, path)
    with wave.open(str(path)) as f:
        assert f.getframerate() == 24000
        assert f.getnframes() == 24000


def test_save_recording_logs_row(tmp_path):
    db = tmp_path / "test.db"
    save_recording(tmp_path / "a.wav", kind="daily", path=db)
    kind = sqlite3.connect(db).execute("SELECT kind FROM recordings").fetchone()[0]
    assert kind == "daily"
