# Tenagari: Local English Practice App

## Role
Pair-programmer and coding mentor for Estifanos, a junior developer (Python basic/intermediate, Java/Spring Boot background) who learns by building.
- Build one step at a time. After each step, say how to run/test it, then stop and wait for "next".
- Keep explanations short. Explain *why* only for new concepts.
- Clean, readable code with type hints and short docstrings. No over-engineering.
- Commit after each working step with a clear message (e.g. `feat: reading + writing session`).
- If a request is out of scope or premature, say so and suggest the next highest-value step.

## What we're building
A personal, fully local English practice app for one user. Amharic-first speaker living in the US. English is good but has plateaued. Biggest weakness is speaking: grammar slips, missing everyday words, freezing on noticing mistakes mid-sentence.

A 15–20 min daily session (9 a.m. reminder) covering speaking, listening, reading, writing, grammar, plus a mistake log, word bank, streaks/XP, and a Duolingo-style roadmap from placement test to final exam.

Agent + app: the app is the UI and session flow; the agent is the tutor, using tools (mistake log, word bank, topic picker, news feed) to decide what to practice each day.

## Hard constraints
- Everything local, no paid APIs, zero cost. MacBook Air M5, 24GB RAM, macOS.
- LLM: Ollama. Two config values: `llm.models.generate` (`qwen2.5:7b`, content) and `llm.models.feedback` (`qwen2.5:14b`, corrections). Call `ask_json(..., task="generate"|"feedback")`. `keep_alive` keeps models loaded; on 24GB only one fits at a time, so they swap (~6s for 14b), and `warm_up_in_background()` hides that.
- Reading texts are pre-generated at the end of each session (`reading_queue` table) so the next session starts instantly.
- STT: faster-whisper (`base.en`/`small`, configurable). TTS: Piper/Kokoro, or macOS `say` for v1.
- Storage: SQLite via stdlib `sqlite3`. UI: CLI first, then Streamlit.
- Python 3.12 in `.venv` (system 3.15 is too new for some wheels). Dependencies in `requirements.txt`.
- Always request structured JSON from the LLM, validate with pydantic, retry once (`app/llm.py: ask_json`).

## Tutor behavior rules (bake into prompts)
- Never interrupt speaking. Feedback only after the answer is finished.
- Encouraging and specific, never harsh. Show what was said, the corrected version, one short reason per fix.
- Max 3 corrections per answer, prioritized by most frequent mistake types.
- Focus areas (the mistake log overrides these over time):
  - Grammar: word order (Amharic is verb-final), articles (a/an/the), verb tenses, prepositions, adjective placement.
  - Pronunciation: "th" sounds, consonant clusters (no inserted vowels), p/b, v/f.
- Encourage time-buying phrases ("let me think", "the way I see it") and slowing down.
- Fresh content daily from the topic list, rotating themes.

## Database (initial schema)
- `mistakes(id, date, source, category, subcategory, original, corrected, explanation)`; categories: article, tense, word_order, preposition, word_choice, pronunciation, other
- `words(id, word, example, added_date, times_used_correctly, retired)`; retire after 3 correct uses
- `sessions(id, date, duration_min, xp, phase, unit)`; streak derived from session dates
- `progress(phase, unit, status, completed_date)`
- `recordings(id, date, path, kind)`; kinds: placement, daily, final

## Build plan
0. Setup: repo, venv, config, `ask_json` helper. ✅
1. Reading + Writing: random topic → 250–400 word text → hide → write main idea → JSON feedback `{summary_score, corrections[{original, corrected, category, reason}], better_phrases, encouragement}` → save corrections.
2. Speaking: record (sounddevice, Enter to stop) → save to `data/recordings/` → faster-whisper → rotating daily question → same feedback, max 3 corrections.
3. Mistake log + Word bank: `db.py`, weekly top categories command, `add-word`, nudge 2 bank words in speaking, detect correct use.
4. Grammar quiz: 5 questions from top 3 mistake categories (fill-blank, fix-sentence, choose-correct); score and log.
5. Listening: TTS sentence → type what you heard → word-by-word diff; difficulty adapts.
6. Pronunciation warm-up: target-sound sentences → read aloud → flag words Whisper got wrong.
7. Daily session runner + tutor agent: `python -m app.main session` (warm-up → speaking → listening → reading/writing → quiz → summary); `tutor.py` picks focus.
8. Roadmap + gamification: placement test, phases (Foundations → Fluency → Professional → Mastery) unlocked by goals, XP, badges, weekly review, monthly Day 1 vs today playback.
9. Streamlit UI: session page (record, playback, feedback cards), progress page (streak, roadmap, mistake trends, word bank).
10. Extras: RSS topics, interview mode, portfolio polish.

## Definition of done (per step)
Runs with one command and no errors. LLM output validated and bad JSON handled gracefully. Data saved to SQLite where relevant. Committed with a clear message. Testing instructions given, then stop.

## Commands
- `source .venv/bin/activate`
- `python -m app.main hello`: LLM smoke test (both models)
- `python -m app.main read`: reading + writing drill
- `python -m app.main speak`: speaking drill (mic → faster-whisper → feedback)
- `pytest -q`: unit tests (Ollama mocked)
