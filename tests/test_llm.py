"""Unit tests for ask_json. Ollama is mocked, so no model is needed."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.llm import LLMError, ask_json
from app.schemas import HelloResponse

GOOD = '{"greeting": "Hello!", "language": "English"}'
BAD = '{"greeting": "Hello!"}'  # missing "language"


def fake_reply(content: str) -> SimpleNamespace:
    """Mimic the shape of ollama.chat's response."""
    return SimpleNamespace(message=SimpleNamespace(content=content))


def test_valid_json_first_try():
    with patch("app.llm.ollama.chat", return_value=fake_reply(GOOD)) as chat:
        result = ask_json("hi", HelloResponse)
    assert result.language == "English"
    assert chat.call_count == 1


def test_retry_after_bad_json():
    with patch("app.llm.ollama.chat", side_effect=[fake_reply(BAD), fake_reply(GOOD)]) as chat:
        result = ask_json("hi", HelloResponse)
    assert result.greeting == "Hello!"
    assert chat.call_count == 2


def test_raises_after_two_bad_replies():
    with patch("app.llm.ollama.chat", return_value=fake_reply(BAD)):
        with pytest.raises(LLMError):
            ask_json("hi", HelloResponse)


def test_connection_error_is_friendly():
    with patch("app.llm.ollama.chat", side_effect=ConnectionError):
        with pytest.raises(LLMError, match="Ollama"):
            ask_json("hi", HelloResponse)
