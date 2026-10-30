"""Speaking drill: answer a daily question out loud, get feedback afterwards."""

from datetime import date

from app.db import save_mistakes, save_recording
from app.llm import ask_json, warm_up_in_background
from app.prompts import TUTOR_SYSTEM
from app.recorder import new_recording_path, record_until_enter
from app.schemas import Feedback, SpeakingQuestion
from app.sessions.common import show_feedback
from app.stt import transcribe
from app.topics import pick_topic

THEMES = {
    "everyday": "a question about his daily life, habits, or opinions on ordinary things",
    "interview": "a common job interview question for a software developer",
    "storytelling": "a request to tell a short story from his own life (a past experience)",
    "debate": "a debate question where he must pick a side and give reasons",
}
MIN_WORDS = 5


def theme_for(day: date) -> str:
    """Rotate themes by calendar day so each day feels different."""
    names = list(THEMES)
    return names[day.toordinal() % len(names)]


def generate_question(theme: str, topic: str) -> SpeakingQuestion:
    """Ask the fast model for one open question he can talk about for 1-2 minutes."""
    prompt = (
        f"Write ONE speaking practice question: {THEMES[theme]}. "
        f"Connect it to this topic if it fits naturally: {topic}.\n"
        "It must be open-ended (not yes/no) and answerable in 1-2 minutes.\n"
        "Also give starter_phrase: a natural time-buying phrase to begin the answer, "
        'like "Let me think... " or "The way I see it, ".\n'
        'Return JSON with "question" and "starter_phrase".'
    )
    return ask_json(prompt, SpeakingQuestion, temperature=0.9, task="generate")


def get_feedback(question: str, transcript: str) -> Feedback:
    """Ask the tutor to correct the spoken answer (from its transcript)."""
    prompt = (
        f"Question: {question}\n\n"
        f"Transcript of his spoken answer (from speech recognition):\n\"\"\"\n{transcript}\n\"\"\"\n\n"
        "This is SPEECH, not writing: ignore punctuation, capitalization, filler words "
        "(um, uh, like), and repeated words from self-correction.\n"
        "1. corrections: up to 3 real English mistakes (grammar, articles, tenses, word order, "
        "prepositions, word choice). Do not use the pronunciation category.\n"
        "2. better_phrases: 2-3 natural phrases a native speaker would use to answer this question.\n"
        "3. encouragement: one or two warm, specific sentences about what he did well."
    )
    return ask_json(prompt, Feedback, system=TUTOR_SYSTEM, task="feedback")


def run() -> None:
    """Run one speaking drill end to end."""
    theme = theme_for(date.today())
    print(f"Today's speaking theme: {theme}\nThinking of a question...\n")
    q = generate_question(theme, pick_topic())

    print(f"❓ {q.question}\n")
    print(f'Tip: no rush. Start with "{q.starter_phrase}" and speak slowly.')
    print("Mistakes are fine. Keep going, and feedback comes only after you finish.\n")
    input("Press Enter to start recording...")

    warm_up_in_background("feedback")  # load the feedback model while you talk
    path = new_recording_path("speaking")
    seconds = record_until_enter(path)
    save_recording(path, kind="daily")
    print(f"Saved {seconds:.0f}s of audio. Transcribing...")

    transcript = transcribe(path)
    if len(transcript.split()) < MIN_WORDS:
        print("I couldn't hear much. Check your mic and try again: python -m app.main speak")
        return

    print(f'\nWhat I heard:\n"{transcript}"\n\nChecking your English...')
    feedback = get_feedback(q.question, transcript)
    show_feedback(feedback)

    saved = save_mistakes(feedback.corrections, source="speaking")
    if saved:
        print(f"\n({saved} mistake(s) saved to your log.)")
