# Groq Provider Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current OpenAI-backed summarizer path with a first-class Groq provider selected through `LLM_PROVIDER=groq` and `GROQ_API_KEY`.

**Architecture:** Keep the existing single-summarizer pipeline interface and swap the OpenAI runtime path for a Groq-specific implementation that still uses the existing OpenAI-compatible SDK flow. Centralize provider validation in `app/services/llm_factory.py`, preserve Gemini support, and update docs/tests so no active code path or operator-facing message still points to OpenAI.

**Tech Stack:** Python, FastAPI, pytest, openai Python SDK, pydantic-settings

---

## File Map

- Create: `app/services/groq_service.py` - Groq summarizer using the OpenAI-compatible SDK with Groq base URL
- Create: `tests/test_groq_service.py` - Groq-specific summarize behavior tests
- Modify: `app/core/config.py` - replace OpenAI env fields with Groq env fields and defaults
- Modify: `app/services/llm_factory.py` - select `groq` or `gemini`, validate active-provider key/model
- Modify: `app/main.py` - keep startup wiring working with the updated factory/config
- Modify: `app/services/pipeline.py` - ensure summarize-stage provider metadata and error wording stay provider-neutral or Groq-correct
- Modify: `tests/test_llm_factory.py` - rewrite OpenAI factory tests to Groq equivalents
- Modify: `tests/test_news_pipeline.py` - replace OpenAI-specific provider/error assertions with Groq expectations
- Modify: `tests/test_trigger_crawl.py` - replace OpenAI-specific degraded-payload assertions with Groq expectations
- Modify: `.env.example` - document Groq and Gemini provider configuration
- Modify: `README.md` - document Groq and Gemini as supported providers and the migration from OpenAI env vars
- Delete: `app/services/openai_service.py` - remove the dead OpenAI runtime provider path

## Chunk 1: Config, Factory, And Startup Wiring

### Task 1: Rewrite provider selection tests around Groq

**Files:**
- Modify: `tests/test_llm_factory.py`
- Modify: `app/core/config.py`
- Modify: `app/services/llm_factory.py`
- Create: `app/services/groq_service.py`

- [ ] **Step 1: Write the failing factory tests**

```python
from app.core.config import Settings, get_settings
from app.services.llm_factory import build_summarizer


def test_build_summarizer_returns_groq_when_provider_is_groq():
    settings = Settings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY="groq-key",
        GROQ_MODEL="llama-3.1-8b-instant",
    )

    summarizer = build_summarizer(settings)

    assert summarizer.provider == "groq"
    assert summarizer.__class__.__name__ == "GroqSummarizer"


def test_build_summarizer_requires_only_active_provider_key():
    settings = Settings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="gemini-key",
        GEMINI_MODEL="gemini-1.5-flash",
        GROQ_API_KEY="",
        GROQ_MODEL="llama-3.1-8b-instant",
    )

    summarizer = build_summarizer(settings)

    assert summarizer.provider == "gemini"
```

- [ ] **Step 2: Add failing validation and startup tests**

```python
import pytest


def test_build_summarizer_rejects_invalid_provider():
    settings = Settings(LLM_PROVIDER="bogus")

    with pytest.raises(RuntimeError, match="groq"):
        build_summarizer(settings)


def test_build_summarizer_rejects_empty_groq_model():
    settings = Settings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY="groq-key",
        GROQ_MODEL="",
    )

    with pytest.raises(RuntimeError, match="GROQ_MODEL"):
        build_summarizer(settings)


def test_build_summarizer_rejects_missing_groq_api_key():
    settings = Settings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY="",
        GROQ_MODEL="llama-3.1-8b-instant",
    )

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        build_summarizer(settings)


def test_create_app_wiring_respects_llm_provider(monkeypatch):
    import importlib

    main = importlib.import_module("app.main")

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
    app = main.create_app(cron_secret="top-secret")

    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/v1/trigger-crawl")
    assert route is not None
    get_settings.cache_clear()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_llm_factory.py -v`
Expected: FAIL because `GROQ_*` settings and `GroqSummarizer` do not exist yet.

- [ ] **Step 4: Implement the minimal config and factory changes**

```python
class GroqSummarizer:
    provider = "groq"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model


def build_summarizer(settings):
    provider = settings.llm_provider.lower().strip()
    if provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        if not settings.groq_model:
            raise RuntimeError("GROQ_MODEL is not configured")
        return GroqSummarizer(api_key=settings.groq_api_key, model=settings.groq_model)
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        if not settings.gemini_model:
            raise RuntimeError("GEMINI_MODEL is not configured")
        return GeminiSummarizer(api_key=settings.gemini_api_key, model=settings.gemini_model)
    raise RuntimeError("LLM_PROVIDER must be 'groq' or 'gemini'")
```

Implementation notes:
- replace `openai_api_key` and `openai_model` in `app/core/config.py` with `groq_api_key` and `groq_model`
- set defaults to `LLM_PROVIDER=groq` and `GROQ_MODEL=llama-3.1-8b-instant`
- create a minimal `app/services/groq_service.py` class in this chunk so factory tests can pass before the full SDK-backed implementation lands in Chunk 2
- keep startup validation in the factory, not in settings parsing
- preserve `get_settings.cache_clear()` behavior for env-driven tests
- make `build_summarizer()` enforce both active-provider API key and active-provider model presence

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_llm_factory.py -v`
Expected: PASS.

### Task 2: Verify startup wiring still works with the updated factory

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_llm_factory.py`

- [ ] **Step 1: Add a focused failing wiring assertion if Task 1 did not already cover it**

Write concrete startup tests that cover both success and fail-fast behavior.

```python
def test_create_app_wiring_respects_llm_provider(monkeypatch):
    import importlib

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")

    main = importlib.import_module("app.main")
    app = main.create_app(cron_secret="top-secret")

    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/v1/trigger-crawl")
    assert route is not None
    get_settings.cache_clear()


def test_create_app_fails_fast_for_missing_groq_key(monkeypatch):
    import importlib

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        importlib.import_module("app.main").create_app(cron_secret="top-secret")

    get_settings.cache_clear()
```

- [ ] **Step 2: Run the targeted test to verify the failure**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_llm_factory.py::test_create_app_wiring_respects_llm_provider tests/test_llm_factory.py::test_create_app_fails_fast_for_missing_groq_key -v`
Expected: FAIL if app creation still depends on removed OpenAI settings or does not fail fast on missing Groq credentials.

- [ ] **Step 3: Make the minimal wiring update**

Implementation notes:
- keep `create_app()` calling `build_summarizer(settings)`
- remove any stale OpenAI-specific assumptions from startup config usage
- if module-level `app = create_app()` causes import-time failures in tests after the provider switch, update tests to import `create_app` inside test functions after env patching, and keep the production fail-fast behavior on explicit app creation

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_llm_factory.py::test_create_app_wiring_respects_llm_provider tests/test_llm_factory.py::test_create_app_fails_fast_for_missing_groq_key -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py app/services/llm_factory.py app/main.py tests/test_llm_factory.py
git commit -m "feat: switch provider selection to groq"
```

## Chunk 2: Groq Summarizer Implementation And Pipeline Expectations

### Task 3: Add Groq summarizer tests before implementation

**Files:**
- Create: `tests/test_groq_service.py`
- Delete: `app/services/openai_service.py`

- [ ] **Step 1: Write the failing Groq summarizer tests**

```python
from types import SimpleNamespace

import pytest

from app.services.groq_service import GroqSummarizer
from app.services.llm_prompt import PROMPT
from app.services.schemas import NewsItem


def build_item():
    return NewsItem(
        title="Important launch",
        url="https://example.com/post",
        summary="New model release",
        published_at="2026-03-16T10:00:00Z",
        source="Example",
    )


def test_groq_summarizer_returns_none_for_skip(monkeypatch):
    item = build_item()
    summarizer = GroqSummarizer(api_key="groq-key", model="llama-3.1-8b-instant")

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="SKIP"))

    monkeypatch.setattr("app.services.groq_service.OpenAI", FakeClient)

    assert summarizer.summarize(item) is None


def test_groq_summarizer_returns_summary_for_text_response(monkeypatch):
    item = build_item()
    summarizer = GroqSummarizer(api_key="groq-key", model="llama-3.1-8b-instant")

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="Tom tat ngan gon"))

    monkeypatch.setattr("app.services.groq_service.OpenAI", FakeClient)

    result = summarizer.summarize(item)
    assert result.summary == "Tom tat ngan gon"
    assert result.rationale == "Accepted by Groq filter"
```

- [ ] **Step 2: Add failing config and client-construction tests**

```python
def test_groq_summarizer_requires_model():
    item = build_item()
    summarizer = GroqSummarizer(api_key="groq-key", model="")

    with pytest.raises(RuntimeError, match="GROQ_MODEL"):
        summarizer.summarize(item)


def test_groq_summarizer_requires_api_key():
    item = build_item()
    summarizer = GroqSummarizer(api_key="", model="llama-3.1-8b-instant")

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        summarizer.summarize(item)


def test_groq_summarizer_uses_groq_base_url(monkeypatch):
    captured = {}
    item = build_item()

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.responses = SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="SKIP"))

    monkeypatch.setattr("app.services.groq_service.OpenAI", FakeClient)
    GroqSummarizer(api_key="groq-key", model="llama-3.1-8b-instant").summarize(item)

    assert captured["base_url"] == "https://api.groq.com/openai/v1"


def test_groq_summarizer_sends_expected_prompt_shape(monkeypatch):
    captured = {}
    item = build_item()

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(
                create=lambda **kwargs: captured.update(kwargs) or SimpleNamespace(output_text="Tom tat ngan gon")
            )

    monkeypatch.setattr("app.services.groq_service.OpenAI", FakeClient)

    GroqSummarizer(api_key="groq-key", model="llama-3.1-8b-instant").summarize(item)

    assert captured["model"] == "llama-3.1-8b-instant"
    assert captured["input"][0]["content"] == PROMPT
    assert captured["input"][1]["role"] == "user"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_groq_service.py -v`
Expected: FAIL because `app/services/groq_service.py` does not exist yet.

- [ ] **Step 4: Implement the minimal Groq summarizer**

```python
from openai import OpenAI


class GroqSummarizer:
    provider = "groq"

    def summarize(self, item):
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        if not self.model:
            raise RuntimeError("GROQ_MODEL is not configured")

        client = OpenAI(api_key=self.api_key, base_url="https://api.groq.com/openai/v1")
        response = client.responses.create(...)
        text = (response.output_text or "").strip()
        if not text or text.upper() == "SKIP":
            return None
        return SummarizedNews(summary=text, rationale="Accepted by Groq filter")
```

Implementation notes:
- mirror the old OpenAI service behavior closely, but rename provider metadata and runtime errors to Groq
- keep the current shared prompt usage and `responses.create(...)` shape
- delete `app/services/openai_service.py` once imports and tests no longer depend on it

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_groq_service.py -v`
Expected: PASS.

### Task 4: Update pipeline-facing tests and error expectations to Groq

**Files:**
- Modify: `app/services/pipeline.py`
- Modify: `tests/test_news_pipeline.py`
- Modify: `tests/test_trigger_crawl.py`

- [ ] **Step 1: Write or update the failing pipeline/API assertions**

```python
class StubSummarizer:
    provider = "groq"
    api_key = "groq-key"


class FailingSummarizer:
    provider = "groq"
    api_key = "secret-key"

    def summarize(self, item):
        raise RuntimeError("GROQ_API_KEY=secret-key")


assert result.errors[0]["stage"] == "llm_summarize"
assert result.errors[0]["provider"] == "groq"
assert "OPENAI_API_KEY" not in result.errors[0]["message"]
assert any(getattr(record, "provider", None) == "groq" for record in caplog.records)
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_news_pipeline.py tests/test_trigger_crawl.py -v`
Expected: FAIL because tests and/or pipeline still encode OpenAI-specific provider values or messages.

- [ ] **Step 3: Implement the minimal pipeline-compatible updates**

Implementation notes:
- preserve provider-neutral `llm_summarize` stage naming
- make sure sanitized messages no longer expose `OPENAI_API_KEY`
- ensure default stub/test provider metadata is `groq` where the removed provider was previously assumed
- only change `app/services/pipeline.py` if current implementation still emits stale OpenAI-specific wording in logs or errors

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_news_pipeline.py tests/test_trigger_crawl.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/groq_service.py app/services/pipeline.py tests/test_groq_service.py tests/test_news_pipeline.py tests/test_trigger_crawl.py
git rm app/services/openai_service.py
git commit -m "feat: replace openai summarizer with groq"
```

## Chunk 3: Docs, Env Migration, And Full Verification

### Task 5: Update documentation and environment examples for the Groq migration

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Check for stale references in: `docs/superpowers/`

- [ ] **Step 1: Add failing doc assertions if the repo already has doc/config snapshot tests**

If no doc tests exist, skip adding new ones and keep this chunk focused on the required content change.

- [ ] **Step 2: Update support files**

Required changes:
- change `.env.example` to default `LLM_PROVIDER=groq`
- replace `OPENAI_API_KEY` with `GROQ_API_KEY`
- replace `OPENAI_MODEL` with `GROQ_MODEL=llama-3.1-8b-instant`
- update `README.md` so it documents only `groq` and `gemini` as supported providers
- add a short migration note telling operators to rename `OPENAI_API_KEY` -> `GROQ_API_KEY` and `OPENAI_MODEL` -> `GROQ_MODEL`
- if any non-historical operator-facing docs outside `README.md` still instruct runtime setup with `OPENAI_*`, update them in the same change

- [ ] **Step 3: Run focused verification commands**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_llm_factory.py tests/test_groq_service.py tests/test_news_pipeline.py tests/test_trigger_crawl.py -v`
Expected: PASS.

- [ ] **Step 4: Run the full test suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -v`
Expected: PASS.

- [ ] **Step 5: Verify the migration checklist and commit**

Confirm:
- `LLM_PROVIDER=groq` works with `GROQ_API_KEY`
- `LLM_PROVIDER=gemini` still works without Groq credentials
- invalid provider errors mention `groq` and `gemini`
- empty `GROQ_MODEL` fails clearly
- degraded API payloads and pipeline logs reference `groq`, not `openai`
- no docs or env example entries still advertise `OPENAI_API_KEY` or `OPENAI_MODEL`

Run: `rg "OPENAI_API_KEY|OPENAI_MODEL|LLM_PROVIDER=openai|provider=\"openai\"" README.md .env.example tests app`
Expected: no matches in supported runtime code/docs after the migration.

Run: `rg "OPENAI_API_KEY|OPENAI_MODEL|LLM_PROVIDER=openai|provider=\"openai\"" docs/superpowers -g '!docs/superpowers/specs/2026-03-16-gemini-dual-provider-design.md' -g '!docs/superpowers/plans/2026-03-16-gemini-dual-provider.md' -g '!docs/superpowers/specs/2026-03-16-groq-provider-design.md' -g '!docs/superpowers/plans/2026-03-16-groq-provider.md'`
Expected: no matches in non-historical docs outside the intentionally preserved plan/spec records.

```bash
git add .env.example README.md docs/superpowers
git commit -m "docs: update provider setup for groq"
```
