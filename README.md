# AI News Crawler

FastAPI service that collects AI news from RSS feeds and Hacker News, filters it with Groq or Gemini, stores processed URLs in Supabase, and pushes summaries to Telegram.

It supports a public Telegram bot flow: users can open a private chat, send `/start`, and receive the latest approved AI news automatically.

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

Telegram and trigger settings:

- `TELEGRAM_BOT_TOKEN=<your bot token>`
- `TELEGRAM_WEBHOOK_SECRET=<random secret>`
- `CRON_SECRET=<random secret>`
- `TELEGRAM_CHAT_ID=<optional legacy fallback chat id>`

If you were previously using OpenAI-compatible env vars, migrate them as follows:

- `OPENAI_API_KEY` -> `GROQ_API_KEY`
- `OPENAI_MODEL` -> `GROQ_MODEL`

`CRON_SECRET_KEY` still works as a legacy compatibility alias for `CRON_SECRET`.

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
- AWS Machine Learning Blog
- Google Research Blog
- Engineering at Meta
- VentureBeat AI
- MIT News AI
- BAIR Blog
- MIT Technology Review AI
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

create table if not exists telegram_subscribers (
  id uuid primary key default gen_random_uuid(),
  chat_id text unique not null,
  username text,
  first_name text,
  is_active boolean not null default true,
  subscribed_at timestamptz not null default now(),
  unsubscribed_at timestamptz,
  last_delivery_at timestamptz,
  delivery_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists telegram_deliveries (
  id uuid primary key default gen_random_uuid(),
  news_url text not null,
  chat_id text not null,
  status text not null,
  delivered_at timestamptz,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (news_url, chat_id)
);
```

## Public Telegram bot setup

1. Create a bot with BotFather and set `TELEGRAM_BOT_TOKEN`.
2. Set `TELEGRAM_WEBHOOK_SECRET` to a random secret value.
3. Deploy this FastAPI app to a public HTTPS URL.
4. Register the webhook:

```bash
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -d "url=https://your-domain.com/api/v1/telegram/webhook" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Supported commands:

- `/start`
- `/stop`
- `/status`
- `/help`

`TELEGRAM_CHAT_ID` remains optional and is only used as a legacy fallback delivery target when no active subscribers exist yet.
