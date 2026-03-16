# Observability Design For AI News Crawler

## Goal

Add first-pass operational observability to the crawler so hourly runs are diagnosable from hosted stdout logs without introducing external services or a metrics backend.

## Scope

This design covers:

- Structured stdout logs
- Per-run correlation with a generated `run_id`
- Source-level success and failure reporting
- Pipeline result enrichment for partial failure visibility
- Tests for the new observability behavior

This design does not cover:

- Prometheus metrics
- External error tracking
- Dashboards or alerting
- Detailed per-item decision logging beyond operational failures

## Current Problems

- The API returns only aggregate counters, so operators cannot tell whether one source failed while the overall run still returned `200`.
- RSS and Hacker News source failures are swallowed, making partial degradation invisible.
- Pipeline failures increment counters but do not emit structured runtime logs.
- There is no run correlation id to connect API trigger, crawler activity, and downstream delivery/persistence failures.

## Recommended Approach

Use a single shared structured logger for the request lifecycle and pipeline execution.

This keeps observability simple for an MVP while making each cron run traceable from start to finish. The system will continue tolerating partial source failures, but it will expose them in both logs and the trigger response.

## Architecture

### Interface Changes

The implementation should use these explicit signatures:

- endpoint generates `run_id`
- `NewsPipeline.run(*, run_id: str) -> PipelineResult`
- `NewsCrawler.fetch_recent_entries(*, run_id: str) -> CrawlerFetchResult`
- `RSSCrawler.fetch_recent_entries(*, run_id: str) -> CrawlerFetchResult`
- `HackerNewsCrawler.fetch_recent_entries(*, run_id: str) -> CrawlerFetchResult`
- `MultiSourceCrawler.fetch_recent_entries(*, run_id: str) -> CrawlerFetchResult`

Test doubles should be updated to accept the same keyword-only `run_id` parameter.

### Logging Layer

Add a lightweight logging helper in `app/core/logging.py` that:

- configures Python `logging` for stdout
- emits JSON-style key/value messages suitable for hosted log streams
- provides a helper for attaching consistent fields such as `event` and `run_id`

The formatter should stay minimal and dependency-free. The output only needs to be structured enough to search and filter reliably.

Bootstrap rule:

- initialize logging once during app creation in `app/main.py`
- logger setup must be idempotent so tests, reloads, or repeated `create_app()` calls do not add duplicate handlers
- application code should request named loggers from `app/core/logging.py` instead of configuring handlers in service modules

### Run Context

Generate a `run_id` at the very start of the trigger endpoint for every `POST /api/v1/trigger-crawl` call, before authorization and pipeline work.

The endpoint passes `run_id` into the pipeline. The pipeline then uses the same id for all log events generated during that run.

### Crawler Reporting

Introduce a shared crawler return type, for example `CrawlerFetchResult`, with two fields:

- `items: list[NewsItem]`
- `source_reports: list[SourceReport]`

`SourceReport` should be a small typed structure used by `RSSCrawler`, `HackerNewsCrawler`, and `MultiSourceCrawler`. For each source, capture:

- source identifier
- source type (`rss` or `hackernews`)
- status (`success` or `failed`)
- number of items collected
- error message when failed

Recommended `SourceReport` shape:

- `source_id: str`
- `source_name: str`
- `source_type: str`
- `status: str`
- `items_collected: int`
- `error: str | None`

Source identity rules:

- RSS: use the feed URL as stable `source_id`, with feed title as optional `source_name`
- Hacker News: use `hackernews` as `source_id`, with `Hacker News` as `source_name`

This metadata feeds both logs and the final pipeline result.

To make downstream pipeline failure logs implementable, extend `NewsItem` with source provenance fields carried from crawler output through the full pipeline:

- `source_id: str`
- `source_name: str`
- `source_type: str`

`source_name` must always be populated. If a human-readable feed title is unavailable, fall back to `source_id`.

Source counting rules are fixed:

- each RSS feed URL counts as one source
- Hacker News counts as one source
- `MultiSourceCrawler` does not count as a source itself; it only aggregates child `source_reports`
- `sources_total` is the number of child source reports collected for the run
- `sources_succeeded` and `sources_failed` are derived from `status` values in those reports
- if Hacker News `/topstories.json` fails, record one failed `SourceReport` for `hackernews` with `items_collected=0` and continue the run

### Pipeline Reporting

Expand `PipelineResult` with operational observability fields:

- `run_id`
- `sources_total`
- `sources_succeeded`
- `sources_failed`
- `source_failures` as a short list of source/error pairs

`source_failures` should use a fixed structured schema:

- `source_id: str`
- `source_name: str`
- `source_type: str`
- `error: str`

The list should include every failed source for the run.

Existing counters remain in place:

- `total_fetched`
- `skipped_existing`
- `skipped_irrelevant`
- `failed_processing`
- `failed_delivery`
- `sent`

`run_id` flow is explicit:

1. `app/api/endpoints.py` generates `run_id`
2. the endpoint calls `pipeline.run(run_id=run_id)`
3. the pipeline passes `run_id` into crawler and log-emission helpers as needed
4. `PipelineResult` stores `run_id` so the API response and completion log share the same correlation id

### API Response

The trigger endpoint continues returning `200` when the run completes, even if some sources fail, because the system is designed to tolerate partial degradation.

The response payload should include:

- `status: ok`
- full enriched pipeline result
- optional `warnings` array when `sources_failed > 0`

`warnings` should be a list of short strings for human-readable summaries, for example:

- `"1 source failed during crawl"`
- `"See result.source_failures for details"`

Detailed failure data lives in `result.source_failures`, which remains the structured field that tests and callers should rely on.

For unexpected hard failures that abort the run, the endpoint should return `500` with:

- `status: error`
- `run_id`
- `detail`

This keeps terminal failures diagnosable and correlated with logs.

This makes partial failures visible to GitHub Actions logs and manual callers without turning every degraded run into a hard failure.

## Data Flow

1. FastAPI receives authorized trigger request.
2. Endpoint creates `run_id` and logs `crawl_run_started`.
3. Pipeline invokes crawlers with the same `run_id` context.
4. Each source logs either `source_fetch_succeeded` or `source_fetch_failed`.
5. Pipeline logs downstream failures at persistence, summarization, and Telegram delivery stages.
6. Pipeline logs `crawl_run_completed` with final counters and source summary.
7. Endpoint returns enriched result payload, including warnings when relevant.

## Failure Classification

Non-fatal, degrade-and-continue failures:

- one RSS feed fetch fails
- one RSS feed parse fails
- one Hacker News item fetch fails
- summarization fails for one item
- persistence fails for one item
- Telegram send fails for one item
- rollback delete fails after Telegram send failure

Fatal, return-500 failures:

- top-level unexpected exception escapes `NewsPipeline.run()`
- endpoint setup or authorization handling raises an unexpected exception
- logger bootstrap fails during app startup

`MultiSourceCrawler` should aggregate child source failures as non-fatal source reports. It should not convert a child-source failure into a hard failure unless an unexpected exception escapes the aggregation loop itself.

## Log Event Schema

Every log event should include:

- `event`
- `run_id`

Event-specific required fields:

- `crawl_run_started`: `event`, `run_id`
- `source_fetch_succeeded`: `event`, `run_id`, `source_id`, `source_name`, `source_type`, `items_collected`
- `source_fetch_failed`: `event`, `run_id`, `source_id`, `source_name`, `source_type`, `error`
- `pipeline_stage_failed`: `event`, `run_id`, `stage`, `url`, `source_id`, `source_name`, `error`
- `delivery_rollback_failed`: `event`, `run_id`, `url`, `source_id`, `source_name`, `error`
- `crawl_run_failed`: `event`, `run_id`, `stage`, `error`
- `crawl_run_completed`: `event`, `run_id`, `total_fetched`, `sent`, `skipped_existing`, `skipped_irrelevant`, `failed_processing`, `failed_delivery`, `sources_total`, `sources_succeeded`, `sources_failed`

Including exception class name in `error` is preferred if easy to do, but not required for the first version.

Implementation contract for testability:

- the logging helper should attach structured fields via `extra` so they are available on `caplog.records`
- rendered stdout JSON should be derived from those same record attributes
- `run_id` should use `uuid.uuid4().hex`

Canonical output style should be newline-delimited JSON objects written to stdout, for example:

```json
{"event":"source_fetch_failed","run_id":"abc123","source_id":"https://example.com/feed.xml","source_name":"Example Feed","source_type":"rss","error":"ReadTimeout"}
```

## Error Handling

- Missing secrets remain hard failures where already required.
- Source fetch failures remain non-fatal to the entire run, but must be logged and surfaced in the result.
- Persistence and delivery failures must log `url`, `source_id`, `source_name`, `stage`, and an error summary.
- Rollback after Telegram send failure should also log whether delete succeeded or failed.
- Logging itself must never crash the pipeline. Defensive log emission is enough for this MVP; no dedicated fallback subsystem is required.

## Testing Strategy

Add tests for:

- endpoint response includes `run_id` and warning fields when sources fail
- crawler result includes source failure metadata
- pipeline logs completion with enriched counters
- source failure does not abort the run
- delivery rollback path still reports correctly
- unexpected hard failure returns `500` with `run_id` and emits `crawl_run_failed`

Tests should avoid asserting the entire log line format. Instead, assert the presence of key fields or key messages so formatting can evolve without excessive churn.

Planned test placement:

- `tests/test_trigger_crawl.py`: response shape, `run_id`, warnings, degraded-run payload
- `tests/test_rss_crawler_runtime.py`: RSS `CrawlerFetchResult` and `SourceReport` behavior
- `tests/test_hackernews_crawler.py`: Hacker News `CrawlerFetchResult` and `SourceReport` behavior
- `tests/test_news_pipeline.py`: summary counters and `caplog.records` assertions for completion/failure events
- app/logging tests: repeated `create_app()` or logging setup calls do not attach duplicate handlers

Use `caplog.records` as the primary assertion surface for log tests. Do not require tests to parse stdout JSON directly.

## Implementation Notes

- Keep the logger helper dependency-free; avoid adding a full observability stack for this MVP.
- Prefer one logging module and one result model update rather than scattering ad-hoc `print` or plain logger calls.
- Preserve current deployment assumptions: logs go to stdout and are read from platform log viewers.

## Risks And Trade-Offs

- Returning `200` on partial degradation avoids noisy cron failures, but it requires operators to actually inspect warnings/logs.
- Structured logs without a formal schema are simple to add now, but may need refinement if the project later adopts centralized logging.
- Source-level metadata adds some complexity to crawler return types, but it is the cleanest way to make partial failures observable.

## Success Criteria

The design is successful when:

- every crawl run has a searchable `run_id`
- operators can tell which source failed from logs and API output
- partial failures no longer appear as silent success
- the implementation remains lightweight and platform-friendly
