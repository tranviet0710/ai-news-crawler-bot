# Public Telegram Bot Design

Date: 2026-03-21

## Goal

Turn the existing AI news crawler into a public Telegram bot that any user can install by starting a private chat with the bot and sending `/start`. Subscribed users receive the latest approved AI news as immediate push notifications.

## Product Decision

- Distribution model: public bot with `/start` and `/stop`
- Delivery mode: immediate push notifications
- Audience model: self-service subscription in private chat

## Current Project Context

The current repository already provides these core capabilities:

- FastAPI app entrypoint and API routes
- Crawling AI news from RSS feeds and Hacker News
- LLM-based filtering and summarization using Groq or Gemini
- Deduplication of processed news in Supabase
- Telegram message formatting and delivery
- Scheduled triggering through GitHub Actions or an authenticated API endpoint

The main gap is that Telegram delivery is currently oriented around a single configured chat target, not a public subscriber model.

## Recommended Approach

Use a subscriber-backed public bot with a Telegram webhook handled by the existing FastAPI service.

### Why this approach

- Reuses the existing service architecture instead of introducing a separate worker or bot runtime
- Allows self-service onboarding through standard Telegram commands
- Scales better than a single hard-coded chat ID
- Leaves room for future features such as per-user preferences, digests, admin commands, and localization

## Alternatives Considered

### 1. Subscriber table plus webhook commands (recommended)

Users message the bot directly. The FastAPI app receives Telegram updates through a webhook, stores subscription status in Supabase, and broadcasts news to all active subscribers.

Pros:

- Best fit for the requested install-and-receive flow
- Keeps the app architecture simple
- Supports clean lifecycle commands (`/start`, `/stop`, `/status`, `/help`)

Cons:

- Requires Telegram webhook configuration and subscriber persistence

### 2. Minimal patch storing chat IDs only

Add `/start` and `/stop`, store chat IDs, and broadcast to that raw list.

Pros:

- Fastest possible implementation

Cons:

- Weak extensibility for preferences, delivery health, and subscriber state tracking
- Harder to maintain as the public bot grows

### 3. Public channel with bot-assisted onboarding

Users follow a Telegram channel, while the bot mainly handles admin tasks or guidance.

Pros:

- Efficient for very large audiences

Cons:

- Does not match the requested direct bot subscription experience as closely

## Architecture

Keep the existing processing pipeline:

1. Trigger crawl
2. Fetch candidate news items
3. Filter and summarize with the selected LLM provider
4. Deduplicate against Supabase
5. Broadcast approved items to active Telegram subscribers
6. Persist processed-news records and delivery metadata

Add a Telegram update ingestion path:

1. Telegram sends user commands to a FastAPI webhook endpoint
2. The app parses the update payload
3. The app updates subscriber state in Supabase
4. The app responds to the user with confirmation or status text

## Components

### `app/api/endpoints.py`

Add a webhook endpoint such as `POST /api/v1/telegram/webhook`.

Responsibilities:

- Receive Telegram updates
- Verify the webhook secret token header
- Route supported commands to the Telegram service layer
- Return a fast success response to Telegram

The existing crawl trigger endpoint remains protected by the cron bearer secret.

### `app/services/telegram_bot.py`

Refactor the Telegram service into two responsibilities:

- Direct responses to one user for command handling
- Broadcast delivery to all active subscribers

Expected functions:

- send_message(chat_id, text, parse_mode)
- handle_start_command(update)
- handle_stop_command(update)
- handle_status_command(update)
- handle_help_command(update)
- broadcast_news(news_item)

The current formatting logic should be preserved where useful, but broadcast delivery must accept a dynamic `chat_id` instead of relying on a single configured destination.

### `app/services/supabase_client.py`

Add subscriber lifecycle operations:

- upsert_subscriber(chat_id, username, first_name)
- deactivate_subscriber(chat_id)
- get_subscriber(chat_id)
- list_active_subscribers()
- mark_delivery_success(chat_id, delivered_at)
- mark_delivery_error(chat_id, error_message)

Keep the existing processed-news operations unchanged except where shared transaction safety or result shape improvements are helpful.

### `app/services/pipeline.py`

Update the notification stage so that every approved news item is broadcast to active subscribers.

Responsibilities:

- Preserve deduplication before delivery
- Fetch active subscribers only after a valid approved item exists
- Attempt delivery to each subscriber independently
- Continue broadcasting when one recipient fails
- Record delivery outcomes for observability

## Data Model

Add a new Supabase table named `telegram_subscribers`.

Suggested schema:

```sql
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
```

Optional future additions:

- language preference
- delivery mode
- admin flag
- last command timestamp

Add a delivery ledger table so broadcast progress is idempotent and observable.

Suggested schema:

```sql
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

Delivery ledger rules:

- create or upsert one row per `(news_url, chat_id)` delivery attempt
- set `status` to values such as `pending`, `sent`, or `failed`
- mark `delivered_at` only after Telegram confirms success
- use the uniqueness rule to prevent duplicate sends when a broadcast is retried after a crash or partial failure

## User-Facing Behavior

### `/start`

- Create or reactivate the subscriber record
- Reply with a short welcome message
- Explain that the bot sends the latest AI news automatically
- Mention `/stop` and `/help`
- Accept subscriptions only from private chats; group and channel contexts should receive a short guidance reply instead of being stored as subscribers

### `/stop`

- Mark the subscriber inactive
- Confirm that notifications are disabled

### `/status`

- Report whether the current chat is subscribed

### `/help`

- Explain available commands and the bot purpose

## Telegram Update Handling

- Treat webhook command handling as idempotent because Telegram can redeliver updates
- Ignore duplicate command effects by making `/start` and `/stop` safe to repeat
- Return success responses quickly after command handling to avoid unnecessary Telegram retries
- Ignore unsupported update types unless a reply is required for user clarity

## Delivery Rules

- Send notifications immediately after a news item is approved by the existing crawl pipeline
- Broadcast only to `is_active = true` subscribers
- Do not fail the entire crawl if one Telegram delivery fails
- Automatically disable a subscriber on hard Telegram errors such as `403 Forbidden: bot was blocked by the user`, `400 Bad Request: chat not found`, or equivalent permanent delivery failures

## Broadcast Execution Semantics

- Keep the crawl trigger request fast by moving subscriber fan-out into a background execution path within the FastAPI app
- The crawl pipeline should first determine the final set of approved news items, then schedule broadcast work for each approved item
- Each recipient send should be independently recorded in `telegram_deliveries`
- If the app crashes mid-broadcast, the next run must resume safely because successful `(news_url, chat_id)` pairs are already marked as `sent`
- Start with sequential or small-batch sending to stay within Telegram limits; add explicit rate limiting if delivery volume grows
- Retry policy for this iteration: do not retry permanent Telegram failures, allow a later crawl run or future enhancement to retry transient failures

## Security

- Keep the existing bearer secret for cron-triggered crawl requests
- Validate the Telegram webhook secret token header for update authenticity
- Avoid adding public broadcast or admin endpoints without authentication
- Keep bot token and webhook secret in environment variables only

## Deployment

### Application

- Deploy the FastAPI service to a public HTTPS host
- Register the Telegram webhook against the deployed endpoint
- Ensure environment variables are configured on the host

### Environment Variables

Required or updated variables:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `CRON_SECRET`
- existing LLM provider configuration variables

Optional:

- `TELEGRAM_CHAT_ID` retained only as a temporary admin/test fallback if desired

## Testing Strategy

Add or update tests for:

- Telegram webhook endpoint accepts valid secret and rejects invalid secret
- `/start` creates or reactivates a subscriber
- `/stop` deactivates a subscriber
- `/status` reports the correct subscription state
- Broadcast sends to multiple active subscribers
- A failed recipient does not stop delivery to the rest
- Existing processed-news deduplication still prevents duplicate sends

## Rollout Plan

1. Add subscriber persistence and service methods
2. Add webhook endpoint and command handling
3. Refactor Telegram delivery to broadcast mode
4. Update pipeline integration and tests
5. Document environment variables and webhook setup
6. Deploy and register the Telegram webhook
7. Verify subscription flow with a test bot account

## Non-Goals For This Iteration

- Per-user topic preferences
- Daily digests
- Rich admin control panel
- Multi-language UX
- Analytics dashboards

## Success Criteria

- A new Telegram user can message the bot and subscribe with `/start`
- The crawler sends newly approved AI news to all active subscribers automatically
- One broken subscriber does not stop delivery to others
- Duplicate news items are still suppressed
- The deployment remains compatible with the existing FastAPI-based architecture
