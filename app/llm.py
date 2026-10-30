"""Ollama client with a structured-JSON helper that validates and retries."""

from typing import TypeVar

import ollama
from pydantic import BaseModel, ValidationError

from app.config import load_config

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Raised when the LLM is unreachable or keeps returning invalid JSON."""


def ask_json(prompt: str, schema: type[T], system: str | None = None) -> T:
    """Ask the local model for JSON matching `schema` and return a validated object.

    Ollama's `format` option constrains the output to the schema. If the reply
    still fails validation, we retry with the error message added to the prompt.
    """
    cfg = load_config()["llm"]
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_error = ""
    for _ in range(1 + cfg.get("max_retries", 1)):
        try:
            response = ollama.chat(
                model=cfg["model"],
                messages=messages,
                format=schema.model_json_schema(),
                options={"temperature": cfg.get("temperature", 0.3)},
            )
        except ConnectionError as e:
            raise LLMError("Can't reach Ollama. Is it running? (open the Ollama app)") from e
        except ollama.ResponseError as e:
            raise LLMError(f"Ollama error: {e.error}") from e

        content = response.message.content or ""
        try:
            return schema.model_validate_json(content)
        except ValidationError as e:
            last_error = str(e)
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": f"Your last reply was invalid JSON for the schema:\n{last_error}\n"
                           "Reply again with only valid JSON.",
            })

    raise LLMError(f"Model returned invalid JSON after retrying: {last_error}")
