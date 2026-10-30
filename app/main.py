"""CLI entry point: `python -m app.main <command>`."""

import argparse
import sys

from app.config import load_config
from app.llm import LLMError, ask_json
from app.schemas import HelloResponse


def cmd_hello() -> None:
    """Smoke test: one structured JSON call to the local model."""
    print(f"Asking {load_config()['llm']['model']}...")
    result = ask_json(
        "Greet an English learner in one short friendly sentence. "
        'Return JSON with "greeting" and "language" (the language of the greeting).',
        HelloResponse,
    )
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser(prog="tenagari", description="Local English practice app")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hello", help="test the LLM connection with a JSON call")
    args = parser.parse_args()

    try:
        if args.command == "hello":
            cmd_hello()
    except LLMError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
