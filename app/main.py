"""CLI entry point: `python -m app.main <command>`."""

import argparse
import sys

from app.llm import LLMError, ask_json, model_for
from app.schemas import HelloResponse
from app.sessions import reading_writing


def cmd_hello() -> None:
    """Smoke test: one structured JSON call to the local model."""
    for task in ("generate", "feedback"):
        print(f"[{task}] asking {model_for(task)}...")
        result = ask_json(
            "Greet an English learner in one short friendly sentence. "
            'Return JSON with "greeting" and "language" (the language of the greeting).',
            HelloResponse,
            task=task,
        )
        print(f"  {result}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="tenagari", description="Local English practice app")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hello", help="test the LLM connection with a JSON call")
    sub.add_parser("read", help="reading + writing drill")
    args = parser.parse_args()

    try:
        if args.command == "hello":
            cmd_hello()
        elif args.command == "read":
            reading_writing.run()
    except LLMError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped. See you next time!")


if __name__ == "__main__":
    main()
