"""Pydantic models describing every JSON shape we expect from the LLM."""

from pydantic import BaseModel


class HelloResponse(BaseModel):
    """Smoke-test response used by `python -m app.main hello`."""

    greeting: str
    language: str
