# Public Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any Telegram user subscribe with `/start` and receive immediate AI news pushes from the existing FastAPI crawler.

**Architecture:** Keep the current FastAPI-based crawler pipeline, but replace single-chat Telegram delivery with a subscriber-backed delivery model. Add a Telegram webhook endpoint for bot commands, extend Supabase with subscriber and delivery-ledger operations, and make pipeline delivery fan out safely to active subscribers while tolerating per-user failures.

**Tech Stack:** Python, FastAPI, Supabase Python client, requests, pytest, httpx

---

## File Map

- Modify: `app/core/config.py`
  - Add webhook secret settings, preserve optional legacy `TELEGRAM_CHAT_ID` fallback behavior, and resolve cron secret naming compatibility.
- Modify: `app/api/endpoints.py`
  - Add Telegram webhook route and secret validation alongside the existing crawl trigger route.
- Modify: `app/main.py`
  - Wire new settings and expanded dependencies into the app factory.
- Modify: `app/services/telegram_bot.py`
  - Split one-user replies from broadcast sending; parse Telegram updates; keep HTML formatting reusable.
- Modify: `app/services/supabase_client.py`
  - Add subscriber and delivery-ledger persistence methods while preserving existing processed-news storage.
- Modify: `app/services/pipeline.py`
  - Broadcast approved items to all active subscribers, record delivery outcomes, and keep crash-safe/idempotent behavior.
- Modify: `README.md`
  - Document new env vars, subscriber schema, webhook registration, and public bot usage.
- Modify: `.env.example`
  - Add `TELEGRAM_WEBHOOK_SECRET` and clarify `TELEGRAM_CHAT_ID` fallback usage.
- Test: `tests/test_config.py`
  - Cover new settings and fallback behavior.
- Test: `tests/test_trigger_crawl.py`
  - Extend router tests for Telegram webhook success and rejection cases.
- Test: `tests/test_news_pipeline.py`
  - Cover multi-subscriber delivery, partial failures, and delivery-ledger interactions.
- Create: `tests/test_telegram_bot.py`
  - Cover Telegram command parsing, private-chat enforcement, and user-facing replies.
- Create: `tests/test_supabase_repository.py`
  - Cover subscriber persistence and delivery-ledger API calls with stubbed clients.

## Chunk 1: Settings and repository foundations

### Task 1: Add configuration coverage for the public bot

**Files:**
- Modify: `app/core/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing settings tests**

Add tests that assert:

```python
def test_settings_reads_telegram_webhook_secret(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "hook-secret")
    settings = Settings()
    assert settings.telegram_webhook_secret == "hook-secret"


def test_settings_keeps_optional_telegram_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    settings = Settings()
    assert settings.telegram_chat_id == "12345"


def test_settings_accepts_legacy_cron_secret_key(monkeypatch):
    monkeypatch.setenv("CRON_SECRET_KEY", "legacy-secret")
    settings = Settings()
    assert settings.cron_secret == "legacy-secret"


def test_settings_reads_canonical_cron_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "new-secret")
    settings = Settings()
    assert settings.cron_secret == "new-secret"
```

- [ ] **Step 2: Run the focused settings tests to verify failure**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_config.py -v`

Expected: failure because `telegram_webhook_secret` does not exist yet.

- [ ] **Step 3: Add the minimal settings fields**

Update `Settings` with:

```python
telegram_webhook_secret: str = Field(default="", alias="TELEGRAM_WEBHOOK_SECRET")
cron_secret: str = Field(default="", alias="CRON_SECRET")
```

Keep `telegram_chat_id` as optional fallback for local/admin delivery tests. Add compatibility logic so `CRON_SECRET` is the documented name while legacy `CRON_SECRET_KEY` still works.

- [ ] **Step 4: Re-run the settings tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_config.py -v`

Expected: PASS.

### Task 2: Extend the Supabase repository for subscribers and delivery ledger

**Files:**
- Modify: `app/services/supabase_client.py`
- Create: `tests/test_supabase_repository.py`

- [ ] **Step 1: Write failing repository tests for subscriber persistence**

Add tests with a fake Supabase client that assert these methods exist and shape requests correctly:

```python
def test_upsert_subscriber_marks_user_active():
    repository = SupabaseNewsRepository(url="https://db", key="key")
    repository._client = fake_client
    repository.upsert_subscriber(chat_id="42", username="viet", first_name="Viet")
    assert fake_client.calls[0] == (
        "telegram_subscribers",
        "upsert",
        {"chat_id": "42", "username": "viet", "first_name": "Viet", "is_active": True},
    )
```

Also cover:

- `deactivate_subscriber(chat_id)`
- `list_active_subscribers()`
- `create_delivery_attempt(news_url, chat_id)` or equivalent upsert method
- `mark_delivery_sent(news_url, chat_id)`
- `mark_delivery_failed(news_url, chat_id, error_message)`
- `delivery_exists(news_url, chat_id)` if you choose to read before send instead of relying purely on upsert constraints

- [ ] **Step 2: Run the focused repository tests to verify failure**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_supabase_repository.py -v`

Expected: failure because the methods do not exist.

- [ ] **Step 3: Implement minimal repository helpers**

Add methods that use dedicated tables:

- `processed_news`
- `telegram_subscribers`
- `telegram_deliveries`

Use explicit table names or configurable constants inside the repository. Keep returned subscriber rows simple, for example:

```python
{"chat_id": "42", "username": "viet", "first_name": "Viet", "is_active": True}
```

Recommended method surface:

```python
def upsert_subscriber(self, chat_id: str, username: str | None, first_name: str | None) -> None: ...
def deactivate_subscriber(self, chat_id: str) -> None: ...
def get_subscriber(self, chat_id: str) -> dict[str, object] | None: ...
def list_active_subscribers(self) -> list[dict[str, object]]: ...
def create_delivery_attempt(self, news_url: str, chat_id: str) -> bool: ...
def mark_delivery_sent(self, news_url: str, chat_id: str) -> None: ...
def mark_delivery_failed(self, news_url: str, chat_id: str, error_message: str) -> None: ...
def deactivate_subscriber_for_delivery_error(self, chat_id: str, error_message: str) -> None: ...
```

Implementation note: `create_delivery_attempt` should return `True` only when the `(news_url, chat_id)` pair is new or retryable, and `False` when already marked as sent. This keeps pipeline fan-out idempotent.

- [ ] **Step 4: Re-run the repository tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_supabase_repository.py -v`

Expected: PASS.

## Chunk 2: Telegram service and webhook command handling

### Task 3: Refactor Telegram bot service for commands and broadcast

**Files:**
- Modify: `app/services/telegram_bot.py`
- Create: `tests/test_telegram_bot.py`

- [ ] **Step 1: Write failing Telegram bot tests**

Add tests for:

```python
def test_build_message_formats_html_news():
    text = bot.build_message(item, ai_summary)
    assert "<b>" in text
    assert "Doc chi tiet" in text


def test_parse_start_command_from_private_chat():
    update = {
        "message": {
            "text": "/start",
            "chat": {"id": 42, "type": "private"},
            "from": {"username": "viet", "first_name": "Viet"},
        }
    }
    result = bot.handle_update(update)
    assert result.action == "subscribe"
    assert result.chat_id == "42"
```

Also cover:

- rejecting non-private chats
- replying with guidance text for non-private chats
- `/stop`
- `/status`
- `/help`
- sending a direct reply with a provided `chat_id`
- sending a broadcast message to an explicit `chat_id`
- classifying Telegram delivery errors into permanent vs transient

- [ ] **Step 2: Run the focused Telegram bot tests to verify failure**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_telegram_bot.py -v`

Expected: failure because command handling is not implemented.

- [ ] **Step 3: Implement the smallest service split that satisfies tests**

Keep one `TelegramBot` class if that matches the codebase style, but give it clear methods such as:

```python
def send_text(self, chat_id: str, text: str) -> None: ...
def send_news(self, chat_id: str, item: NewsItem, ai_summary: SummarizedNews) -> None: ...
def parse_command(self, update: dict[str, object]) -> CommandPayload | None: ...
def build_welcome_message(self) -> str: ...
def build_status_message(self, is_active: bool) -> str: ...
def classify_delivery_error(self, exc: Exception) -> DeliveryError: ...
```

Use a small dataclass like:

```python
@dataclass
class CommandPayload:
    command: str
    chat_id: str
    chat_type: str
    username: str | None
    first_name: str | None


@dataclass
class DeliveryError:
    message: str
    is_permanent: bool
```

Do not add a Telegram framework dependency; keep using `requests`.

For non-private chats, return a parsed command result that tells the webhook layer to send a short guidance reply such as "Please message me in a private chat and use /start there." Do not create a subscriber record for those chats.

- [ ] **Step 4: Re-run the Telegram bot tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_telegram_bot.py -v`

Expected: PASS.

### Task 4: Add the Telegram webhook endpoint

**Files:**
- Modify: `app/api/endpoints.py`
- Modify: `app/main.py`
- Modify: `tests/test_trigger_crawl.py`

- [ ] **Step 1: Write failing webhook endpoint tests**

Add tests that assert:

```python
def test_telegram_webhook_rejects_invalid_secret():
    response = asyncio.run(post(app, "/api/v1/telegram/webhook", headers={"X-Telegram-Bot-Api-Secret-Token": "bad"}, json=update))
    assert response.status_code == 401


def test_telegram_webhook_subscribes_private_user():
    response = asyncio.run(post(app, "/api/v1/telegram/webhook", headers={"X-Telegram-Bot-Api-Secret-Token": "hook"}, json=start_update))
    assert response.status_code == 200
    assert repository.upsert_calls == [("42", "viet", "Viet")]
```

Also cover:

- `/stop` deactivates subscriber
- `/status` reads subscriber state
- `/help` returns a direct reply
- repeated `/start` remains idempotent
- non-private `/start` gets a guidance reply and does not call `upsert_subscriber`

- [ ] **Step 2: Run webhook tests to verify failure**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_trigger_crawl.py -v`

Expected: failure because the route does not exist.

- [ ] **Step 3: Implement minimal webhook plumbing**

Update `build_router` so it can receive:

- `cron_secret`
- `pipeline`
- `telegram_bot`
- `repository`
- `telegram_webhook_secret`

Route responsibilities:

- validate `X-Telegram-Bot-Api-Secret-Token`
- parse the incoming update via `telegram_bot`
- persist subscriber changes through `repository`
- send the user-facing reply with `telegram_bot.send_text(...)`
- return `{"status": "ok"}` even for ignored update types when auth succeeds

Keep the crawl background-task behavior unchanged.

- [ ] **Step 4: Re-run webhook tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_trigger_crawl.py -v`

Expected: PASS.

## Chunk 3: Pipeline fan-out and delivery safety

### Task 5: Convert pipeline delivery to subscriber broadcast

**Files:**
- Modify: `app/services/pipeline.py`
- Modify: `tests/test_news_pipeline.py`

- [ ] **Step 1: Write failing pipeline tests for multi-subscriber delivery**

Add tests like:

```python
def test_news_pipeline_broadcasts_to_all_active_subscribers():
    repository = StubRepository(active_subscribers=[{"chat_id": "1"}, {"chat_id": "2"}])
    telegram = StubTelegram()
    pipeline = NewsPipeline(...)
    result = pipeline.run(run_id="run-123")
    assert result.sent == 2
    assert telegram.messages == [("1", "Important launch"), ("2", "Important launch")]
```

Also cover:

- one subscriber failure does not stop the other recipients
- a hard Telegram delivery failure deactivates the subscriber
- a transient Telegram delivery failure marks the attempt failed but keeps the subscriber active
- ledger prevents duplicate re-send for the same `(news_url, chat_id)` pair
- no rollback deletes of `processed_news` after a partial subscriber delivery failure
- zero active subscribers plus configured legacy `TELEGRAM_CHAT_ID` sends one fallback admin message

- [ ] **Step 2: Run focused pipeline tests to verify failure**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_news_pipeline.py -v`

Expected: failure because the pipeline still uses one `telegram.send(...)` call and rollback delete behavior.

- [ ] **Step 3: Implement minimal broadcast logic**

Change the pipeline order to:

1. skip existing processed news
2. summarize
3. save processed news once
4. fetch active subscribers
5. if there are no active subscribers and legacy `TELEGRAM_CHAT_ID` is configured, use that one fallback target for backward compatibility
6. for each subscriber or fallback target:
   - call `create_delivery_attempt(item.url, chat_id)`
   - skip if already sent
   - call `telegram.send_news(chat_id, item, ai_summary)`
   - on success call `mark_delivery_sent(...)`
   - on failure call `mark_delivery_failed(...)`
   - classify the error via `telegram.classify_delivery_error(...)`
   - on permanent failure for a real subscriber call `deactivate_subscriber_for_delivery_error(...)`

Recommended result accounting:

- `sent`: count successful subscriber deliveries
- `failed_delivery`: count failed subscriber deliveries

Do not delete from `processed_news` when one recipient fails. The item itself has been processed successfully. Do not attempt to deactivate the legacy fallback `TELEGRAM_CHAT_ID`, since it is config-driven rather than subscriber-driven.

- [ ] **Step 4: Re-run the focused pipeline tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_news_pipeline.py -v`

Expected: PASS.

### Task 6: Wire the app factory to the expanded dependencies

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add or update an app factory test if one is missing**

If existing endpoint tests already cover `create_app(...)` wiring, extend them instead of adding a new test file.

- [ ] **Step 2: Implement the minimal wiring change**

Construct shared instances once in `create_app(...)`:

```python
repository = SupabaseNewsRepository(url=settings.supabase_url, key=settings.supabase_key)
telegram_bot = TelegramBot(bot_token=settings.telegram_bot_token, timeout=15)
pipeline = NewsPipeline(..., repository=repository, telegram=telegram_bot)
app.include_router(
    build_router(
        cron_secret=cron_secret or settings.cron_secret,
        pipeline=active_pipeline,
        telegram_bot=telegram_bot,
        repository=repository,
        telegram_webhook_secret=settings.telegram_webhook_secret,
    )
)
```

Retain support for injecting a stub pipeline in tests without forcing real credentials.
Use `settings.cron_secret` as the canonical field name, with compatibility fallback from legacy `CRON_SECRET_KEY` handled inside settings.

- [ ] **Step 3: Run the endpoint tests again**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_trigger_crawl.py -v`

Expected: PASS.

## Chunk 4: Documentation and full verification

### Task 7: Document setup and rollout

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Add a short docs test/checklist entry in the plan**

No automated test required, but verify docs mention:

- `TELEGRAM_WEBHOOK_SECRET`
- `telegram_subscribers` and `telegram_deliveries` schemas
- webhook registration example
- `/start`, `/stop`, `/status`, `/help`
- optional legacy `TELEGRAM_CHAT_ID` fallback note
- canonical `CRON_SECRET` name and legacy `CRON_SECRET_KEY` compatibility note

- [ ] **Step 2: Update docs minimally**

Keep README focused; add only the configuration and deployment details needed for this feature. Show `CRON_SECRET` as the primary variable and mention `CRON_SECRET_KEY` only as a legacy compatibility note.

- [ ] **Step 3: Manually read the changed sections for consistency**

Expected: docs match implementation names and env vars exactly.

### Task 8: Run the targeted and full test suite

**Files:**
- Test: `tests/test_config.py`
- Test: `tests/test_supabase_repository.py`
- Test: `tests/test_telegram_bot.py`
- Test: `tests/test_trigger_crawl.py`
- Test: `tests/test_news_pipeline.py`

- [ ] **Step 1: Run targeted feature tests**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_config.py tests/test_supabase_repository.py tests/test_telegram_bot.py tests/test_trigger_crawl.py tests/test_news_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -v
```

Expected: PASS.

- [ ] **Step 3: Inspect the final diff**

Run: `git diff -- app/core/config.py app/api/endpoints.py app/main.py app/services/telegram_bot.py app/services/supabase_client.py app/services/pipeline.py README.md .env.example tests/test_config.py tests/test_supabase_repository.py tests/test_telegram_bot.py tests/test_trigger_crawl.py tests/test_news_pipeline.py`

Expected: only public bot feature changes and docs updates.
