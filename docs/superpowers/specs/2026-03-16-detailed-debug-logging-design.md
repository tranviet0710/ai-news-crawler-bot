# Detailed Debug Logging Design For AI News Crawler

## Goal

Make every crawler run easy to debug from hosted stdout logs while keeping secrets and sensitive payloads out of logs.

This document supersedes `docs/superpowers/specs/2026-03-16-observability-design.md` for implementation of debug logging and error visibility.

## Scope

This design adds:

- structured stdout logging across API, crawler, pipeline, OpenAI, Supabase, and Telegram
- one `run_id` per trigger request
- stage-level success and failure logs
- short debug error summaries in the API response
- tests that verify logging coverage and secret redaction behavior

This design does not add:

- external logging backends
- full payload dumps
- Prometheus metrics
- dashboards or alerting

## Current Problem

The service currently catches processing and delivery exceptions without logging the exception details. As a result, the response only shows counters such as `failed_processing: 1`, which is not enough to tell whether the root cause is missing OpenAI credentials, Supabase errors, Telegram errors, or remote API failures.

## Recommended Approach

Use one shared structured logger writing to stdout, with safe debug metadata and per-run correlation through `run_id`.

This gives enough information to identify the exact failing stage and item without exposing API keys, bot tokens, chat ids, or full request/response payloads.

## Architecture

### Logging Module

Add `app/core/logging.py` with:

- idempotent logging bootstrap for stdout
- a helper to return named loggers
- a helper to attach structured fields through `extra`
- safe string formatting for exceptions and masked identifiers

Bootstrap should run once from `app/main.py` during app creation.

### Run Correlation

`app/api/endpoints.py` generates `run_id = uuid.uuid4().hex` at the start of every trigger request.

The endpoint passes `run_id` into the pipeline. All downstream logs for that crawl must include the same `run_id`.

### Response Debug Summary

Expand the pipeline result with a bounded `errors` array for quick debugging. Each error entry should include:

- `stage`
- `url`
- `source`
- `error_type`
- `message`
- `recoverable`

Define a typed error entry shape, for example `PipelineErrorEntry`, with exactly these serialized fields:

- `stage: str`
- `url: str`
- `source: str`
- `error_type: str`
- `message: str`
- `recoverable: bool`

This list should be capped to avoid oversized responses. For MVP, cap at 10 entries.

Errors should be appended in encounter order during pipeline processing. When more than 10 errors occur, keep the first 10 appended entries in `result.errors` and increment `suppressed_error_count` for each later error.

`recoverable` rules are fixed:

- item-level and source-level failures that still allow the run to continue use `recoverable: true`
- unexpected top-level request failures are not added to `result.errors`; they are handled by the top-level `500` response and use `trigger_crawl_failed`

The response stays operationally simple:

- `status`
- `run_id`
- `result`

but `result` now includes both counters and `errors`.

Successful or partial-success responses should use this shape:

```json
{
  "status": "ok",
  "run_id": "<uuid4 hex>",
  "result": {
    "total_fetched": 1,
    "skipped_existing": 0,
    "skipped_irrelevant": 0,
    "sent": 0,
    "failed_delivery": 0,
    "failed_processing": 1,
    "suppressed_error_count": 0,
    "errors": []
  }
}
```

Unexpected top-level failures should return:

```json
{
  "status": "error",
  "run_id": "<uuid4 hex>",
  "detail": "Unexpected crawl failure"
}
```

The detailed failure reason belongs in logs, not in the public error response.

## Interface Changes

Use these explicit signatures:

- `NewsPipeline.run(*, run_id: str) -> PipelineResult`
- `NewsCrawler.fetch_recent_entries(*, run_id: str)`
- `RSSCrawler.fetch_recent_entries(*, run_id: str)`
- `HackerNewsCrawler.fetch_recent_entries(*, run_id: str)`
- `MultiSourceCrawler.fetch_recent_entries(*, run_id: str)`

Test doubles should accept the same keyword-only `run_id` parameter.

## Logging Coverage

### API Events

`app/api/endpoints.py` should log:

- `trigger_crawl_started`
- `trigger_crawl_authorized`
- `trigger_crawl_unauthorized`
- `trigger_crawl_finished`
- `trigger_crawl_failed`

Fields:

- `event`
- `run_id`
- `status_code` where relevant
- final result counters on completion

### Pipeline Events

`app/services/pipeline.py` should log:

- `pipeline_started`
- `item_check_exists_started`
- `item_skipped_existing`
- `openai_summarize_started`
- `openai_summarize_succeeded`
- `openai_summarize_failed`
- `item_skipped_irrelevant`
- `supabase_save_started`
- `supabase_save_succeeded`
- `supabase_save_failed`
- `telegram_send_started`
- `telegram_send_succeeded`
- `telegram_send_failed`
- `rollback_delete_started`
- `rollback_delete_succeeded`
- `rollback_delete_failed`
- `pipeline_completed`

Common fields for item-level events:

- `event`
- `run_id`
- `url`
- `source`
- `title`
- `stage` where relevant

Failure events must also include:

- `error_type`
- `message`

### Crawler Events

`app/services/crawler.py` should log:

- `source_fetch_started`
- `source_fetch_succeeded`
- `source_fetch_failed`
- `crawler_completed`

Fields:

- `event`
- `run_id`
- `source_id`
- `source_type`
- `items_collected`
- `error_type` and `message` on failure

### Service Metadata Events

Ownership rule: pipeline logs are required and are the authoritative stage logs. Service-internal logs are optional and should only be added where they provide unique metadata not already available in pipeline logs.

If service-internal logs are added, they must receive `run_id` through method parameters or constructor-injected logger adapters.

Optional service-internal logs must follow the same JSON schema and log-level conventions as required pipeline and crawler logs.

Service modules may log additional safe metadata:

- `openai_request_started`: `model`, `url`, `source`
- `openai_request_succeeded`: `model`, `url`
- `supabase_query_started`: `table_name`, `operation`, `url`
- `supabase_query_succeeded`: `table_name`, `operation`, `url`
- `telegram_request_started`: `telegram_api_host`, `url`
- `telegram_request_succeeded`: `telegram_api_host`, `url`

No service may log:

- API keys
- bearer tokens
- raw Telegram bot token
- full chat id
- full OpenAI request or response body
- full Supabase credentials

## Safe Debug Rules

- Exception messages may be logged as plain text only after sanitization.
- The same sanitizer must be applied to stdout logs and to `result.errors.message`.
- API keys, bearer tokens, and Telegram bot tokens must be fully redacted as `[REDACTED]`.
- Chat ids must be masked to keep only the last 4 characters, for example `******1234`.
- URL userinfo, auth fragments, and query parameter values that look secret must be redacted.
- Log only high-value metadata, never raw full payloads.
- If a library exception contains request config, sanitize it before logging.

Add explicit redaction tests for:

- `OPENAI_API_KEY`
- `SUPABASE_KEY`
- Telegram bot token
- bearer token values
- masked chat id behavior

## Log Schema

Every log record should expose structured attributes usable by `caplog.records`:

- `event`
- `run_id`

Field naming rules:

- use `source` for human-readable item source labels in pipeline events and response `errors`
- use `source_id` for stable crawler-source identifiers such as feed URL or `hackernews`
- use `source_type` for classifier values such as `rss` or `hackernews`

Additional event-specific fields should be attached via `extra`, not only embedded in the rendered string.

Rendered output should be newline-delimited JSON on stdout.

Example:

```json
{"event":"openai_summarize_failed","run_id":"8b7d...","url":"https://example.com/post","source":"OpenAI Blog","title":"Fresh launch","error_type":"RuntimeError","message":"OPENAI_API_KEY is not configured"}
```

## Error Handling Rules

- partial item failures stay non-fatal to the whole run
- source fetch failures stay non-fatal when other sources can continue
- unexpected top-level pipeline exceptions should log `trigger_crawl_failed` and return `500`
- logging failures themselves must never crash the request path

If a top-level exception occurs, the endpoint must still include the already-generated `run_id` in the `500` response.

Logging bootstrap failure during app startup is not a request-time `500`; it is an application startup failure and should fail fast during startup.

## Testing Strategy

Add tests for:

- `tests/test_trigger_crawl.py`: response includes bounded `errors` entries when processing fails
- `tests/test_trigger_crawl.py`: successful responses include `run_id`
- `tests/test_news_pipeline.py`: `caplog.records` contains stage-specific failure logs and completion summary
- `tests/test_rss_crawler_runtime.py`: source fetch failures emit source-level logs with `run_id`
- `tests/test_hackernews_crawler.py`: source fetch failures emit source-level logs with `run_id`
- secret values are not present in emitted logs or in `result.errors.message`
- `tests/test_logging.py`: repeated app creation does not duplicate stdout handlers
- `tests/test_trigger_crawl.py`: unexpected top-level failure returns `500` with `run_id`

Tests should assert structured record attributes, not the exact rendered JSON string.

Log levels should be standardized:

- `info` for started/succeeded/completed events
- `warning` for recoverable item or source failures
- `error` for unexpected top-level failures and rollback failures

## Success Criteria

This design is successful when:

- a failed run clearly shows whether it broke at OpenAI, Supabase, Telegram, or a feed source
- every error log can be tied to one crawl through `run_id`
- the API response exposes short debug context without dumping sensitive internals
- logs remain safe to use in hosted environments
