# AI News Crawler

FastAPI service that pulls recent AI news from RSS feeds and Hacker News, filters and summarizes each item with Groq or Gemini, stores processed items in Supabase, and delivers approved updates to Telegram.

It supports two delivery modes:

- public Telegram bot subscriptions via `/start`, `/stop`, `/status`, and `/help`
- a legacy fallback chat configured with `TELEGRAM_CHAT_ID` when no active subscribers exist yet

## What it does

1. Fetches recent entries from configured RSS feeds and optionally Hacker News.
2. Skips URLs already saved in Supabase.
3. Uses the selected LLM provider to reject irrelevant stories or generate a short summary.
4. Saves accepted items to Supabase.
5. Sends each accepted item to active Telegram subscribers and records delivery status.

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

## Requirements

- Python 3.12+
- Supabase project
- Telegram bot token
- One LLM provider:
  - Groq
  - Gemini

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then fill in `.env`.

## Configuration

### Required settings

| Variable | Required when | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | always | `groq` or `gemini` |
| `GROQ_API_KEY` | `LLM_PROVIDER=groq` | required for Groq summarization |
| `GROQ_MODEL` | `LLM_PROVIDER=groq` | defaults to `llama-3.1-8b-instant` |
| `GEMINI_API_KEY` | `LLM_PROVIDER=gemini` | required for Gemini summarization |
| `GEMINI_MODEL` | `LLM_PROVIDER=gemini` | defaults to `gemini-2.5-flash` |
| `SUPABASE_URL` | always | Supabase project URL |
| `SUPABASE_KEY` | always | Supabase API key |
| `TELEGRAM_BOT_TOKEN` | always | used for webhook replies and news delivery |
| `TELEGRAM_WEBHOOK_SECRET` | webhook mode | checked on `/api/v1/telegram/webhook` |
| `CRON_SECRET` | scheduled crawling | bearer token for `/api/v1/trigger-crawl` |

### Optional settings

| Variable | Default | Notes |
| --- | --- | --- |
| `TELEGRAM_CHAT_ID` | empty | legacy fallback target when there are no active subscribers |
| `CRAWL_LOOKBACK_HOURS` | `24` in `.env.example` | code default is `2` if unset |
| `RSS_SOURCES` | built-in list | comma-separated feed URLs; include the Hacker News top stories URL to enable the HN crawler |

### Provider examples

Groq:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=<your key>
GROQ_MODEL=llama-3.1-8b-instant
```

Gemini:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=<your key>
GEMINI_MODEL=gemini-2.5-flash
```

### Legacy compatibility

- `CRON_SECRET_KEY` still works as an alias for `CRON_SECRET`
- if you were previously using OpenAI-compatible names, migrate:
  - `OPENAI_API_KEY` -> `GROQ_API_KEY`
  - `OPENAI_MODEL` -> `GROQ_MODEL`

## Run locally

```bash
uvicorn app.main:app --reload
```

The app exposes:

- `GET /health`
- `POST /api/v1/trigger-crawl`
- `POST /api/v1/telegram/webhook`

## Trigger a crawl manually

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/trigger-crawl" \
  -H "Authorization: Bearer <CRON_SECRET>"
```

The endpoint returns `202 Accepted` and runs the crawl in the background.

## Telegram bot setup

1. Create a bot with BotFather and set `TELEGRAM_BOT_TOKEN`.
2. Set `TELEGRAM_WEBHOOK_SECRET` to a random secret value.
3. Deploy this app to a public HTTPS URL.
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

Group chats are not supported for subscriptions; the bot replies with guidance to continue in a private chat.

## Scheduled execution

`.github/workflows/cronjob.yml` triggers the crawl every 4 hours and can also be run manually with `workflow_dispatch`.

The workflow expects these GitHub secrets:

- `API_URL`
- `CRON_SECRET`

`API_URL` should point to the deployed trigger endpoint, for example:

```text
https://your-domain.com/api/v1/trigger-crawl
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
