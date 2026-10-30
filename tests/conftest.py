"""Test safety: never touch the real database or start background processes."""

import os
import tempfile

# Must run before any `app` import: db.DB_PATH is read from this env var at import time.
os.environ["TENAGARI_DB"] = os.path.join(tempfile.mkdtemp(prefix="tenagari-test-"), "test.db")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def no_background_processes(monkeypatch):
    """Fail loudly if code under test tries to spawn a process (e.g. prepare-quiz)."""
    def refuse(*args, **kwargs):
        raise AssertionError(f"test tried to start a process: {args[0] if args else kwargs}")
    monkeypatch.setattr("subprocess.Popen", refuse)
