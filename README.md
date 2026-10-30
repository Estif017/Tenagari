# Tenagari

A personal, fully local English practice app: speaking, listening, reading, writing and grammar in a 15–20 minute daily session, with a local AI tutor behind it.

Everything runs on your machine: Ollama (LLM), faster-whisper (speech-to-text), local TTS, SQLite. No paid APIs.

## Setup

```bash
ollama pull qwen2.5:7b
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m app.main hello   # smoke test: one JSON call to the local model
pytest -q                  # unit tests
```

Settings (model, topics, session lengths) live in `config.yaml`.
