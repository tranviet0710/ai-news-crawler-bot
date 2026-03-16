# Gemini Dual-Provider Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Gemini support alongside OpenAI with provider selection controlled by `LLM_PROVIDER`.

**Architecture:** Keep the pipeline on a single summarizer interface and add a provider factory that builds either OpenAI or Gemini at app startup. Extract the shared prompt into a common module, keep provider request code isolated, and update debug logging to use provider-neutral summarize stage names plus a `provider` field.

**Tech Stack:** Python, FastAPI, pytest, OpenAI SDK, Google Gen AI SDK, pydantic-settings

---

## File Map

- Create: `app/services/gemini_service.py` - Gemini summarizer implementation
- Create: `app/services/llm_factory.py` - provider selection and startup validation
- Create: `app/services/llm_prompt.py` - shared summarize/filter prompt
- Create: `tests/test_llm_factory.py` - provider selection and validation tests
- Create: `tests/test_gemini_service.py` - Gemini-specific behavior tests
- Modify: `app/services/openai_service.py` - reuse shared prompt, expose provider metadata
- Modify: `app/core/config.py` - add `LLM_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL`
- Modify: `app/main.py` - build summarizer via factory
- Modify: `app/services/pipeline.py` - provider-neutral summarize stage names and provider field in logs/errors
- Modify: `tests/test_news_pipeline.py` - assert provider-neutral summarize stage and provider field
- Modify: `tests/test_trigger_crawl.py` - assert provider-neutral `llm_summarize` stage in API payloads if needed
- Modify: `.env.example` - add provider config variables
- Modify: `requirements.txt` - add Gemini SDK dependency
- Modify: `README.md` - document provider config and provider-specific secrets

## Chunk 1: Config And Factory

### Task 1: Add failing tests for provider settings and factory selection

**Files:**
- Create: `tests/test_llm_factory.py`
- Modify: `app/core/config.py`
- Create: `app/services/llm_factory.py`

- [ ] **Step 1: Write the failing factory tests**

```python
from app.core.config import Settings
from app.services.llm_factory import build_summarizer
from app.services.openai_service import OpenAISummarizer
from app.services.gemini_service import GeminiSummarizer


def test_build_summarizer_returns_openai_when_provider_is_openai():
    settings = Settings(
        LLM_PROVIDER="openai",
        OPENAI_API_KEY="key",
        OPENAI_MODEL="gpt-4.1-mini",
    )

    summarizer = build_summarizer(settings)

    assert isinstance(summarizer, OpenAISummarizer)


def test_build_summarizer_returns_gemini_when_provider_is_gemini():
    settings = Settings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="key",
        GEMINI_MODEL="gemini-1.5-flash",
    )

    summarizer = build_summarizer(settings)

    assert isinstance(summarizer, GeminiSummarizer)
```

- [ ] **Step 2: Add failing validation tests**

```python
def test_build_summarizer_rejects_invalid_provider():
    settings = Settings(LLM_PROVIDER="bogus")

    with pytest.raises(RuntimeError):
        build_summarizer(settings)


def test_build_summarizer_requires_only_active_provider_key():
    settings = Settings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="gem-key",
        GEMINI_MODEL="gemini-1.5-flash",
        OPENAI_API_KEY="",
    )

    summarizer = build_summarizer(settings)

    assert summarizer.provider == "gemini"
```

- [ ] **Step 3: Run factory tests to verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_llm_factory.py -v`
Expected: FAIL because Gemini factory/config do not exist yet

- [ ] **Step 4: Implement minimal config and factory**

```python
def build_summarizer(settings):
    if settings.llm_provider == "openai":
        ...
    if settings.llm_provider == "gemini":
        ...
    raise RuntimeError("Unsupported LLM_PROVIDER")
```

Implementation notes:
- add `llm_provider`, `gemini_api_key`, and `gemini_model` to `Settings`
- validate missing active-provider key/model in `build_summarizer(settings)`
- keep inactive-provider credentials optional

- [ ] **Step 5: Run factory tests to verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_llm_factory.py -v`
Expected: PASS

## Chunk 2: Shared Prompt And Provider Implementations

### Task 2: Add failing tests for Gemini summarizer and shared prompt usage

**Files:**
- Create: `app/services/llm_prompt.py`
- Create: `app/services/gemini_service.py`
- Create: `tests/test_gemini_service.py`
- Modify: `app/services/openai_service.py`

- [ ] **Step 1: Write the failing Gemini summarizer tests**

```python
def test_gemini_summarizer_returns_none_for_skip(monkeypatch):
    summarizer = GeminiSummarizer(api_key="key", model="gemini-1.5-flash")
    ...
    assert summarizer.summarize(item) is None


def test_gemini_summarizer_returns_summary_for_text_response(monkeypatch):
    summarizer = GeminiSummarizer(api_key="key", model="gemini-1.5-flash")
    ...
    result = summarizer.summarize(item)
    assert result.summary == "Tom tat"
```

- [ ] **Step 2: Add failing Gemini error-path tests**

```python
def test_gemini_summarizer_raises_for_empty_text(monkeypatch):
    summarizer = GeminiSummarizer(api_key="key", model="gemini-1.5-flash")

    with pytest.raises(RuntimeError):
        summarizer.summarize(item)
```

- [ ] **Step 3: Run Gemini tests to verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_gemini_service.py -v`
Expected: FAIL because Gemini service and shared prompt do not exist yet

- [ ] **Step 4: Implement shared prompt and minimal provider code**

Implementation notes:
- move prompt text from `app/services/openai_service.py` into `app/services/llm_prompt.py`
- give both providers `provider` metadata
- use `google-genai` in `app/services/gemini_service.py`
- make Gemini map `SKIP` to `None`
- make blocked/empty/no-usable-text outcomes raise `RuntimeError`

- [ ] **Step 5: Run provider tests to verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_gemini_service.py -v`
Expected: PASS

## Chunk 3: App Wiring And Provider-Neutral Logging

### Task 3: Add failing tests for startup wiring and provider-neutral summarize stage names

**Files:**
- Modify: `app/main.py`
- Modify: `app/services/pipeline.py`
- Modify: `tests/test_news_pipeline.py`
- Modify: `tests/test_trigger_crawl.py`

- [ ] **Step 1: Write the failing app wiring test**

```python
def test_create_app_uses_gemini_provider_when_configured(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-flash")
    ...
```

- [ ] **Step 2: Write the failing provider-neutral pipeline tests**

```python
assert result.errors[0]["stage"] == "llm_summarize"
assert any(record.event == "llm_summarize_failed" for record in caplog.records)
assert any(record.provider == "gemini" for record in caplog.records)
```

- [ ] **Step 3: Run wiring and pipeline tests to verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_news_pipeline.py tests/test_trigger_crawl.py -v`
Expected: FAIL because app still hardcodes OpenAI and summarize stage names are OpenAI-specific

- [ ] **Step 4: Implement factory wiring and provider-neutral summarize logging**

Implementation notes:
- replace direct `OpenAISummarizer(...)` construction in `app/main.py` with `build_summarizer(settings)`
- ensure tests can clear cached settings before rebuilding app
- rename summarize-stage log/event names and API error stage from `openai_summarize` to `llm_summarize`
- include `provider=self.summarizer.provider` in summarize-related logs

- [ ] **Step 5: Run updated wiring and pipeline tests to verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_news_pipeline.py tests/test_trigger_crawl.py -v`
Expected: PASS

## Chunk 4: Docs, Env Example, Dependencies, Full Verification

### Task 4: Finalize support files and verify full behavior

**Files:**
- Modify: `.env.example`
- Modify: `requirements.txt`
- Modify: `README.md`

- [ ] **Step 1: Write a failing dependency/docs smoke test if needed**

If practical, add a minimal test that imports the Gemini service module without runtime errors once dependency declarations are in place.

- [ ] **Step 2: Update support files**

Required changes:
- add `LLM_PROVIDER`, `GEMINI_API_KEY`, and `GEMINI_MODEL` to `.env.example`
- add `google-genai` to `requirements.txt`
- update `README.md` to document:
  - provider selection via `LLM_PROVIDER`
  - provider-specific required secrets
  - dual-provider support

- [ ] **Step 3: Run the full test suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -v`
Expected: PASS

- [ ] **Step 4: Verify behavior checklist**

Confirm:
- `LLM_PROVIDER=openai` works without Gemini credentials
- `LLM_PROVIDER=gemini` works without OpenAI credentials
- invalid provider fails clearly
- missing active-provider key/model fails clearly
- Gemini summarize failures surface as `llm_summarize`
- summarize logs include `provider`

- [ ] **Step 5: Re-run full test suite after any final adjustments**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -v`
Expected: PASS
