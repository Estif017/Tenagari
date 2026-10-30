"""CLI entry point: `python -m app.main <command>`."""

import argparse
import sys

from app.db import RETIRE_AFTER, latest_mistake, list_words, top_mistake_categories
from app.llm import LLMError, ask_json, model_for
from app.schemas import HelloResponse
from app.sessions import reading_writing, speaking
from app.word_bank import add_with_example


def cmd_hello(args: argparse.Namespace) -> None:
    """Smoke test: one structured JSON call to each local model."""
    for task in ("generate", "feedback"):
        print(f"[{task}] asking {model_for(task)}...")
        result = ask_json(
            "Greet an English learner in one short friendly sentence. "
            'Return JSON with "greeting" and "language" (the language of the greeting).',
            HelloResponse,
            task=task,
        )
        print(f"  {result}")


def cmd_mistakes(args: argparse.Namespace) -> None:
    """Show the top mistake categories for the last N days, with a recent example of each."""
    top = top_mistake_categories(days=args.days, limit=7)
    if not top:
        print(f"No mistakes logged in the last {args.days} days. Do a session first!")
        return
    print(f"Your top mistakes (last {args.days} days):\n")
    biggest = top[0][1]
    for category, count in top:
        bar = "█" * max(1, round(20 * count / biggest))
        print(f"  {category:<13} {bar} {count}")
        example = latest_mistake(category)
        if example:
            print(f"  {'':<13} e.g. \"{example['original']}\" → \"{example['corrected']}\"")
    print(f"\nFocus for now: {top[0][0]}")


def cmd_add_word(args: argparse.Namespace) -> None:
    """Add a word or phrase to the word bank."""
    added, info = add_with_example(args.word, args.example)
    if not added:
        print(f'"{args.word}" is already in your word bank.')
        return
    print(f'Added "{args.word}".')
    if info:
        print(f"  Meaning: {info.meaning}\n  Example: {info.example}")


def cmd_words(args: argparse.Namespace) -> None:
    """List the word bank."""
    words = list_words(include_retired=args.all)
    if not words:
        print('Your word bank is empty. Add one: python -m app.main add-word "come up with"')
        return
    for w in words:
        status = "🎓 learned" if w["retired"] else f"{w['times_used_correctly']}/{RETIRE_AFTER}"
        print(f"  {w['word']:<22} {status}")
        if w["example"]:
            print(f"  {'':<22} {w['example']}")


COMMANDS = {
    "hello": cmd_hello,
    "read": lambda args: reading_writing.run(),
    "speak": lambda args: speaking.run(),
    "mistakes": cmd_mistakes,
    "add-word": cmd_add_word,
    "words": cmd_words,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="tenagari", description="Local English practice app")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hello", help="test the LLM connection with a JSON call")
    sub.add_parser("read", help="reading + writing drill")
    sub.add_parser("speak", help="speaking drill (uses the mic)")
    p = sub.add_parser("mistakes", help="top mistake categories")
    p.add_argument("--days", type=int, default=7)
    p = sub.add_parser("add-word", help='add a word or phrase: add-word "come up with"')
    p.add_argument("word")
    p.add_argument("--example", help="your own example sentence (otherwise one is generated)")
    p = sub.add_parser("words", help="list your word bank")
    p.add_argument("--all", action="store_true", help="include learned (retired) words")
    args = parser.parse_args()

    try:
        COMMANDS[args.command](args)
    except LLMError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped. See you next time!")


if __name__ == "__main__":
    main()
