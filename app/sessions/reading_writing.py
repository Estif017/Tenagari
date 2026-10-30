"""Reading + writing drill: read a text, hide it, summarize it, get feedback."""

from app.db import pop_reading, queue_reading, reading_queue_size, save_mistakes
from app.llm import ask_json, warm_up_in_background
from app.prompts import TUTOR_SYSTEM
from app.schemas import ReadingText, WritingFeedback
from app.topics import pick_topic

CLEAR_SCREEN = "\033[2J\033[H"


def generate_text(topic: str) -> ReadingText:
    """Ask the model for a fresh upper-intermediate reading passage."""
    prompt = (
        f"Write an original article about: {topic}. Pick a specific, interesting angle.\n"
        "Length: 4 paragraphs, 250-400 words in total. Level: upper-intermediate (B2). "
        "Use natural, everyday vocabulary with a few useful new words. "
        "It must have one clear main idea. "
        'Return JSON with "title" and "text" (paragraphs separated by blank lines).'
    )
    return ask_json(prompt, ReadingText, temperature=0.8, task="generate")


def get_feedback(passage: ReadingText, summary: str) -> WritingFeedback:
    """Ask the tutor to score the summary and correct its English."""
    prompt = (
        f"Original text:\n\"\"\"\n{passage.text}\n\"\"\"\n\n"
        f"Student's summary of the main idea, written from memory:\n\"\"\"\n{summary}\n\"\"\"\n\n"
        "1. summary_score (0-10): how well the summary captures the main idea. "
        "Judge content ONLY here.\n"
        "2. corrections: up to 3 English mistakes in the STUDENT'S summary "
        "(grammar, articles, tenses, word choice). Not about content.\n"
        "3. better_phrases: 2-3 natural phrases he could have used.\n"
        "4. encouragement: one or two warm, specific sentences."
    )
    return ask_json(prompt, WritingFeedback, system=TUTOR_SYSTEM, task="feedback")


def read_multiline(prompt: str) -> str:
    """Read lines until the user enters an empty line."""
    print(prompt)
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines).strip()


def show_feedback(fb: WritingFeedback) -> None:
    """Print feedback cards to the terminal."""
    print(f"\n=== Feedback ===\nMain idea score: {fb.summary_score}/10\n")
    if fb.corrections:
        for i, c in enumerate(fb.corrections, 1):
            print(f"{i}. You wrote:  {c.original}")
            print(f"   Better:     {c.corrected}")
            print(f"   Why:        {c.reason}  [{c.category}]\n")
    else:
        print("No corrections. Your English was clean!\n")
    if fb.better_phrases:
        print("Phrases to try:")
        for p in fb.better_phrases:
            print(f"  - {p}")
    print(f"\n{fb.encouragement}")


def get_todays_text() -> tuple[str, ReadingText]:
    """Use a pre-generated text if one is queued; otherwise generate one now."""
    queued = pop_reading()
    if queued:
        print(f"Today's topic: {queued[0]} (prepared yesterday)\n")
        return queued
    topic = pick_topic()
    print(f"Today's topic: {topic}\nGenerating a text...\n")
    return topic, generate_text(topic)


def prepare_next_text(today_topic: str) -> None:
    """Pre-generate the next session's text (different topic) if the queue is empty."""
    if reading_queue_size() > 0:
        return
    topic = pick_topic(exclude=today_topic)
    print("\nPreparing tomorrow's text so your next session starts instantly...")
    queue_reading(topic, generate_text(topic))
    print(f"Ready. Tomorrow's topic: {topic}")


def run() -> None:
    """Run one reading + writing drill end to end."""
    topic, passage = get_todays_text()
    warm_up_in_background("feedback")  # load the feedback model while you read

    print(f"=== {passage.title} ===\n\n{passage.text}\n")
    input("Read it carefully. Press Enter to hide the text...")
    print(CLEAR_SCREEN, end="")

    summary = read_multiline("Write the main idea in your own words (press Enter on an empty line to finish):")
    if summary:
        print("\nChecking your writing...")
        feedback = get_feedback(passage, summary)
        show_feedback(feedback)

        saved = save_mistakes(feedback.corrections, source="reading_writing")
        if saved:
            print(f"\n({saved} mistake(s) saved to your log.)")
    else:
        print("No summary written. Skipping feedback.")

    prepare_next_text(today_topic=topic)
