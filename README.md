# AI News Crawler

FastAPI service that collects AI news from RSS feeds and Hacker News, filters it with Groq or Gemini, stores processed URLs in Supabase, and pushes summaries to Telegram.

## Project structure

```text
app/
  api/
  core/
  services/
tests/
.github/workflows/cronjob.yml
requirements.txt
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `LLM_PROVIDER` to `groq` or `gemini`. Only the active provider key is required for summarization.

Default local setup uses Groq:

- `LLM_PROVIDER=groq`
- `GROQ_API_KEY=<your key>`
- `GROQ_MODEL=llama-3.1-8b-instant`

Gemini remains supported with:

- `LLM_PROVIDER=gemini`
- `GEMINI_API_KEY=<your key>`
- `GEMINI_MODEL=gemini-2.5-flash`

If you were previously using OpenAI-compatible env vars, migrate them as follows:

- `OPENAI_API_KEY` -> `GROQ_API_KEY`
- `OPENAI_MODEL` -> `GROQ_MODEL`

## Run locally

```bash
uvicorn app.main:app --reload
```

## Run tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests
```

## Supported sources

- OpenAI Blog
- Google AI Blog
- Anthropic News via RSS hub
- TechCrunch AI
- Hugging Face Blog
- Hacker News top stories API

## Supabase schema

```sql
create extension if not exists "pgcrypto";

create table if not exists processed_news (
  id uuid primary key default gen_random_uuid(),
  url text unique not null,
  title text not null,
  summary text,
  source text,
  published_at timestamptz not null,
  created_at timestamptz not null default now()
);
```
