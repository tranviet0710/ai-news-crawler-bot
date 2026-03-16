# Detailed Debug Logging Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe, detailed structured logging and bounded debug error details so crawl failures can be diagnosed from stdout logs and API responses.

**Architecture:** Introduce one shared logging module, thread a `run_id` through the trigger endpoint and pipeline, capture sanitized error entries in `PipelineResult`, and add stage-level logs in crawler and pipeline code. Keep logging ownership centered in the pipeline/crawler layers, with optional service metadata only if needed.

**Tech Stack:** Python, FastAPI, pytest, standard library logging, uuid, json

---

## Shared Rules

- Keep at most `10` entries in `PipelineResult.errors`
- Append errors in encounter order during processing
- Increment `suppressed_error_count` for every later error after the first 10
- Re-raise `HTTPException` unchanged in `app/api/endpoints.py`; only unexpected exceptions become `500`
- Use one sanitizer helper that performs pattern-based redaction plus exact redaction of known configured secrets passed from settings or service instances

## File Map

- Create: `app/core/logging.py` - logging bootstrap, JSON formatter, sanitizer helpers
- Modify: `app/main.py` - initialize logging once during app creation
- Modify: `app/api/endpoints.py` - generate `run_id`, wrap pipeline execution, return `run_id` and top-level error response
- Modify: `app/services/pipeline.py` - add `PipelineErrorEntry`, `errors`, logging, and `run_id` support
- Modify: `app/services/crawler.py` - add source-level logging and `run_id` plumbing
- Modify: `tests/test_trigger_crawl.py` - endpoint response/logging behavior
- Modify: `tests/test_news_pipeline.py` - pipeline logging and bounded errors
- Modify: `tests/test_rss_crawler_runtime.py` - crawler failure logging
- Modify: `tests/test_hackernews_crawler.py` - crawler failure logging
- Create: `tests/test_logging.py` - logging bootstrap idempotence and sanitization helpers

## Chunk 1: Logging Foundation And Endpoint Wiring

### Task 1: Add failing tests for logging helpers and endpoint response shape

**Files:**
- Create: `tests/test_logging.py`
- Modify: `tests/test_trigger_crawl.py`

- [ ] **Step 1: Write the failing logging helper tests**

```python
def test_mask_secret_redacts_known_values():
    from app.core.logging import sanitize_message

    text = "token=abc123 secret=xyz789"
    sanitized = sanitize_message(text, secrets=["abc123", "xyz789"])

    assert "abc123" not in sanitized
    assert "xyz789" not in sanitized
    assert "[REDACTED]" in sanitized


def test_configure_logging_is_idempotent():
    from app.core.logging import configure_logging

    logger_one = configure_logging()
    logger_two = configure_logging()

    assert logger_one is logger_two
```

- [ ] **Step 2: Run logging helper tests to verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_logging.py -v`
Expected: FAIL because `app.core.logging` does not exist yet

- [ ] **Step 3: Write the failing endpoint response test**

```python
def test_trigger_crawl_returns_run_id_and_errors_when_pipeline_degrades():
    class StubPipeline:
        def run(self, *, run_id):
            return {
                "total_fetched": 1,
                "skipped_existing": 0,
                "skipped_irrelevant": 0,
                "sent": 0,
                "failed_delivery": 0,
                "failed_processing": 1,
                "suppressed_error_count": 0,
                "errors": [
                    {
                        "stage": "openai_summarize",
                        "url": "https://example.com/post",
                        "source": "Example",
                        "error_type": "RuntimeError",
                        "message": "OPENAI_API_KEY is not configured",
                        "recoverable": True,
                    }
                ],
            }
    ...
    assert "run_id" in response.json()
```

Add two more explicit endpoint tests:

```python
def test_trigger_crawl_preserves_http_exceptions():
    class StubPipeline:
        def run(self, *, run_id):
            raise HTTPException(status_code=418, detail="teapot")

    ...
    assert response.status_code == 418
    assert response.json() == {"detail": "teapot"}


def test_trigger_crawl_returns_500_with_run_id_for_unexpected_error():
    class StubPipeline:
        def run(self, *, run_id):
            raise RuntimeError("boom")

    ...
    assert response.status_code == 500
    assert response.json()["status"] == "error"
    assert "run_id" in response.json()
```

- [ ] **Step 4: Run endpoint test to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_trigger_crawl.py::test_trigger_crawl_returns_run_id_and_errors_when_pipeline_degrades -v`
Expected: FAIL because endpoint does not pass `run_id` or return it yet

- [ ] **Step 5: Implement minimal logging module and endpoint wiring**

Implementation notes:
- add `configure_logging()`, `get_logger(name)`, and `sanitize_message()` in `app/core/logging.py`
- make `configure_logging()` attach one stdout handler with JSON output
- call `configure_logging()` in `app/main.py`
- update `app/api/endpoints.py` to generate `uuid.uuid4().hex`, call `pipeline.run(run_id=run_id)`, and return `run_id` in success responses
- catch unexpected top-level exceptions, log `trigger_crawl_failed`, and return `500` with `status`, `run_id`, and generic `detail`

- [ ] **Step 6: Run focused tests to verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_logging.py tests/test_trigger_crawl.py -v`
Expected: PASS

- [ ] **Step 7: Commit checkpoint**

```bash
git add tests/test_logging.py tests/test_trigger_crawl.py app/core/logging.py app/main.py app/api/endpoints.py
git commit -m "feat: add structured trigger logging"
```

## Chunk 2: Pipeline Error Tracking And Stage Logs

### Task 2: Add failing tests for pipeline errors, logs, and sanitizer use

**Files:**
- Modify: `tests/test_news_pipeline.py`
- Modify: `app/services/pipeline.py`

- [ ] **Step 1: Write the failing pipeline tests**

```python
def test_pipeline_records_sanitized_openai_error(caplog):
    class FailingSummarizer:
        def summarize(self, item):
            raise RuntimeError("OPENAI_API_KEY=secret-key")

    pipeline = NewsPipeline(
        crawler=StubCrawler(),
        repository=StubRepository(),
        summarizer=FailingSummarizer(),
        telegram=StubTelegram(),
    )

    result = pipeline.run(run_id="run-123")

    assert result.failed_processing == 1
    assert result.errors[0]["stage"] == "openai_summarize"
    assert "secret-key" not in result.errors[0]["message"]
    assert any(record.event == "openai_summarize_failed" for record in caplog.records)


def test_pipeline_records_exists_failure_as_recoverable_error(caplog):
    class ExistsFailingRepository(StubRepository):
        def exists(self, url):
            raise RuntimeError("SUPABASE_KEY=top-secret")

    pipeline = NewsPipeline(
        crawler=StubCrawler(),
        repository=ExistsFailingRepository(),
        summarizer=StubSummarizer(),
        telegram=StubTelegram(),
    )

    result = pipeline.run(run_id="run-123")

    assert result.failed_processing == 1
    assert result.errors[0]["stage"] == "supabase_exists"
    assert result.errors[0]["recoverable"] is True
    assert any(record.event == "supabase_exists_failed" for record in caplog.records)
```

- [ ] **Step 2: Run targeted pipeline tests to verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_news_pipeline.py -v`
Expected: FAIL because pipeline has no error entries, no run_id, and no logs

- [ ] **Step 3: Implement minimal pipeline changes**

Implementation notes:
- add dataclasses like:

```python
@dataclass
class PipelineErrorEntry:
    stage: str
    url: str
    source: str
    error_type: str
    message: str
    recoverable: bool
```

- add bounded helper like:

```python
def append_error(self, entry: PipelineErrorEntry) -> None:
    if len(self.errors) < 10:
        self.errors.append(asdict(entry))
    else:
        self.suppressed_error_count += 1
```

- log failures with structured records like:

```python
logger.warning(
    "pipeline stage failed",
    extra={
        "event": "openai_summarize_failed",
        "run_id": run_id,
        "url": item.url,
        "source": item.source,
        "error_type": type(exc).__name__,
        "message": sanitized,
    },
)
```

- add `PipelineErrorEntry` dataclass and extend `PipelineResult`
- add helper to append bounded errors in encounter order
- change `NewsPipeline.run(*, run_id: str)` signature
- log `pipeline_started` and `pipeline_completed`
- wrap `repository.exists()`, `summarizer.summarize()`, `repository.save()`, `telegram.send()`, and rollback delete with structured logs
- sanitize exception text before logging and before storing in `errors`
- classify item/source stage failures as `recoverable=True`

- [ ] **Step 4: Run targeted pipeline tests to verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_news_pipeline.py -v`
Expected: PASS

- [ ] **Step 4b: Add and run explicit bounded-error tests**

Add a failing test that forces 12 recoverable failures and asserts:

```python
assert len(result.errors) == 10
assert result.suppressed_error_count == 2
assert result.errors[0]["url"] == "https://example.com/item-0"
assert result.errors[-1]["url"] == "https://example.com/item-9"
```

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_news_pipeline.py::test_pipeline_caps_errors_at_ten_in_encounter_order -v`
Expected: PASS after implementation

- [ ] **Step 5: Commit checkpoint**

```bash
git add tests/test_news_pipeline.py app/services/pipeline.py
git commit -m "feat: add pipeline debug error reporting"
```

## Chunk 3: Source-Level Logging

### Task 3: Add failing tests for crawler logs and run_id propagation

**Files:**
- Modify: `tests/test_rss_crawler_runtime.py`
- Modify: `tests/test_hackernews_crawler.py`
- Modify: `app/services/crawler.py`

- [ ] **Step 1: Write failing crawler log tests**

```python
def test_rss_crawler_logs_source_failure(caplog, monkeypatch):
    def fake_get(url, timeout):
        raise RuntimeError("Bearer abc123")

    monkeypatch.setattr("app.services.crawler.requests.get", fake_get)
    crawler = RSSCrawler(sources=["https://example.com/feed.xml"])

    items = crawler.fetch_recent_entries(run_id="run-123")

    assert items == []
    assert any(record.event == "source_fetch_failed" for record in caplog.records)
    assert all("abc123" not in record.message for record in caplog.records)


def test_hackernews_crawler_logs_topstories_failure(caplog, monkeypatch):
    def fake_get(url, timeout):
        raise RuntimeError("token=hn-secret")

    monkeypatch.setattr("app.services.crawler.requests.get", fake_get)
    crawler = HackerNewsCrawler()

    items = crawler.fetch_recent_entries(run_id="run-123")

    assert items == []
    assert any(record.event == "source_fetch_failed" and record.source_id == "hackernews" for record in caplog.records)
```

- [ ] **Step 2: Run crawler tests to verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_rss_crawler_runtime.py tests/test_hackernews_crawler.py -v`
Expected: FAIL because crawlers do not accept `run_id` or log events yet

- [ ] **Step 3: Implement minimal crawler logging**

Implementation notes:
- update crawler interfaces to accept `run_id`
- log `source_fetch_started`, `source_fetch_succeeded`, and `source_fetch_failed`
- use source URL as `source_id` for RSS and `hackernews` for Hacker News
- keep current tolerant behavior for source failures by having `RSSCrawler` and `HackerNewsCrawler` swallow their own fetch exceptions, log them, and return `[]`

- [ ] **Step 4: Run crawler tests to verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_rss_crawler_runtime.py tests/test_hackernews_crawler.py -v`
Expected: PASS

- [ ] **Step 5: Commit checkpoint**

```bash
git add tests/test_rss_crawler_runtime.py tests/test_hackernews_crawler.py app/services/crawler.py
git commit -m "feat: add crawler source failure logging"
```

## Chunk 4: Full Verification

### Task 4: Verify integrated behavior

**Files:**
- Modify as needed: `README.md` only if endpoint response/logging behavior needs docs

- [ ] **Step 1: Run full test suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -v`
Expected: PASS

- [ ] **Step 2: Inspect test coverage by behavior**

Verify:
- success response includes `run_id`
- degraded response includes bounded `errors`
- top-level failure returns `500` with `run_id`
- `HTTPException` passthrough stays unchanged
- stage failures emit structured log records
- sanitizer redacts secrets in logs and response errors
- configured secret values from service instances are redacted, not only ad hoc secret lists

- [ ] **Step 3: Update docs only if behavior changed materially**

If needed, add a short note in `README.md` describing that `/api/v1/trigger-crawl` returns `run_id` and bounded debug errors for troubleshooting.

- [ ] **Step 4: Re-run full test suite after any doc/code changes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -v`
Expected: PASS

- [ ] **Step 5: Commit final checkpoint**

```bash
git add app tests README.md
git commit -m "feat: add detailed debug logging for crawl pipeline"
```
