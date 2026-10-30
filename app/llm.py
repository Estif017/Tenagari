"""Ollama client with a structured-JSON helper that validates and retries."""

import threading
from typing import Literal, TypeVar

import ollama
from pydantic import BaseModel, ValidationError

from app.config import load_config

T = TypeVar("T", bound=BaseModel)
Task = Literal["generate", "feedback"]


class LLMError(Exception):
    """Raised when the LLM is unreachable or keeps returning invalid JSON."""


def model_for(task: Task) -> str:
    """Return the model name configured for a task ("generate" or "feedback")."""
    return load_config()["llm"]["models"][task]


def warm_up(task: Task) -> None:
    """Load a model into memory ahead of time (an empty prompt just loads it).

    Best effort: errors are ignored, since the real call will report them.
    """
    try:
        ollama.generate(model=model_for(task), keep_alive=load_config()["llm"].get("keep_alive", "5m"))
    except Exception:
        pass


def warm_up_in_background(task: Task) -> None:
    """Start warm_up in a daemon thread so the user isn't kept waiting."""
    threading.Thread(target=warm_up, args=(task,), daemon=True).start()


def ask_json(
    prompt: str,
    schema: type[T],
    system: str | None = None,
    temperature: float | None = None,
    task: Task = "feedback",
) -> T:
    """Ask the local model for JSON matching `schema` and return a validated object.

    Ollama's `format` option constrains the output to the schema. If the reply
    still fails validation, we retry with the error message added to the prompt.
    `task` picks the model: a fast one for generating content, a stronger one
    for feedback. Pass a higher `temperature` for creative content.
    """
    cfg = load_config()["llm"]
    if temperature is None:
        temperature = cfg.get("temperature", 0.3)
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_error = ""
    for _ in range(1 + cfg.get("max_retries", 1)):
        try:
            response = ollama.chat(
                model=model_for(task),
                messages=messages,
                format=schema.model_json_schema(),
                options={"temperature": temperature},
                keep_alive=cfg.get("keep_alive", "5m"),
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
