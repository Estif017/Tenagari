"""Display helpers shared by all session types."""

from app.schemas import Feedback, WritingFeedback


def show_feedback(fb: Feedback) -> None:
    """Print feedback cards to the terminal."""
    print("\n=== Feedback ===")
    if isinstance(fb, WritingFeedback):
        print(f"Main idea score: {fb.summary_score}/10")
    print()
    if fb.corrections:
        for i, c in enumerate(fb.corrections, 1):
            print(f"{i}. You said:  {c.original}")
            print(f"   Better:    {c.corrected}")
            print(f"   Why:       {c.reason}  [{c.category}]\n")
    else:
        print("No corrections. Your English was clean!\n")
    if fb.better_phrases:
        print("Phrases to try:")
        for p in fb.better_phrases:
            print(f"  - {p}")
    print(f"\n{fb.encouragement}")
