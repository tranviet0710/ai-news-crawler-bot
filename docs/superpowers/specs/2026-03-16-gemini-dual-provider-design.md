# Gemini Dual-Provider Design For AI News Crawler

## Goal

Add Gemini support alongside OpenAI, with provider selection controlled by `LLM_PROVIDER` in environment configuration.

## Scope

This design covers:

- selecting `openai` or `gemini` through env vars
- keeping one summarizer interface for the pipeline
- updating config, runtime wiring, tests, and docs
- extending logs to include the active provider during summarize stages

This design does not cover:

- runtime fallback between providers
- per-request provider selection
- Vertex AI integration
- prompt customization per provider beyond minor request-shape differences

## Current State

- The service currently hardcodes `OpenAISummarizer` in `app/main.py`.
- `app/services/openai_service.py` is OpenAI-specific in both naming and implementation.
- Config only supports `OPENAI_API_KEY` and `OPENAI_MODEL`.

## Recommended Approach

Keep the pipeline interface unchanged and introduce a provider adapter layer.

The app will create one summarizer object at startup based on `LLM_PROVIDER`. The pipeline still calls `summarize(item)` without knowing whether OpenAI or Gemini is active.

## Architecture

### Provider Interface

Use one shared summarizer contract, preferably a `Protocol`:

- `summarize(item: NewsItem) -> SummarizedNews | None`
- `provider: str`
- `api_key: str`

Both providers must preserve current behavior:

- return `None` for skipped/irrelevant news
- return `SummarizedNews` for accepted news
- raise a configuration/runtime exception for invalid setup or API failure

### Service Layout

Recommended structure:

- keep `app/services/openai_service.py` for `OpenAISummarizer`
- add `app/services/gemini_service.py` for `GeminiSummarizer`
- add `app/services/llm_factory.py` for provider selection
- add `app/services/llm_prompt.py` for the shared summarization prompt

This keeps provider-specific request code isolated and prevents one service file from becoming a large provider switchboard.

### Configuration

Add these settings in `app/core/config.py`:

- `LLM_PROVIDER` with allowed values `openai` or `gemini`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`

Defaults:

- `LLM_PROVIDER=openai`
- `OPENAI_MODEL` may stay as the current default
- `GEMINI_MODEL=gemini-1.5-flash`

Validation rules:

- if `LLM_PROVIDER=openai`, `OPENAI_API_KEY` is required
- if `LLM_PROVIDER=gemini`, `GEMINI_API_KEY` is required
- invalid provider values should fail fast during app startup via summarizer factory construction in `app/main.py`

Provider-specific credential validation should also happen in `build_summarizer(settings)` during app startup:

- missing active-provider API key is a startup failure
- missing active-provider model name is a startup failure
- inactive-provider credentials are optional and should not be validated

### Runtime Wiring

`app/main.py` should stop instantiating `OpenAISummarizer` directly.

Instead, it should call a factory such as `build_summarizer(settings)` that returns the configured provider implementation.

Startup/testing rule:

- provider validation should happen inside `create_app()` through factory construction
- tests that change env-based provider settings should call `get_settings.cache_clear()` before rebuilding the app or settings object

### Logging

Keep current debug logging design, but include `provider` in summarize-related logs:

- `openai_summarize_started` and `openai_summarize_failed` should become provider-neutral names such as `llm_summarize_started`, `llm_summarize_succeeded`, and `llm_summarize_failed`
- each log should include `provider=openai` or `provider=gemini`

This also changes observable API debug payloads: summarize-related error `stage` values should become `llm_summarize` instead of `openai_summarize`.

Logging naming rule:

- pipeline summarize-stage events should use provider-neutral `llm_*` names plus `provider`
- provider-internal optional request logs may stay provider-specific if needed, but should still include `provider`

This avoids baking OpenAI into log naming once Gemini exists.

### Prompt Strategy

Reuse the same filtering/summarization prompt semantics across both providers by extracting the prompt text into `app/services/llm_prompt.py`.

The prompt content can stay shared unless one provider requires a small formatting adjustment for SDK compatibility. Behavior should remain aligned:

- short Vietnamese summary for relevant AI news
- `SKIP` for irrelevant items

Gemini response handling rules:

- text response `SKIP` => `None`
- non-empty text summary => `SummarizedNews`
- blocked/safety-filtered/empty-candidate/empty-text response => raise runtime error with sanitized detail so the pipeline logs it as a provider failure

Implementation note for Gemini:

- use `from google import genai`
- create client with `genai.Client(api_key=...)`
- send the shared prompt plus article context through the SDK text generation call used for the selected model
- inspect the returned text output as the primary success path
- if the SDK returns no usable text or indicates blocked output, raise a runtime error describing the non-success outcome

## API And Pipeline Impact

No API shape change is required for this feature.

The pipeline remains unchanged except for receiving provider-aware logging fields from the summarizer stage.

## Testing Strategy

Add tests for:

- factory returns `OpenAISummarizer` when `LLM_PROVIDER=openai`
- factory returns `GeminiSummarizer` when `LLM_PROVIDER=gemini`
- missing provider-specific key raises the correct error
- invalid `LLM_PROVIDER` raises a clear error
- inactive-provider key is not required
- Gemini summarizer maps `SKIP` to `None`
- pipeline/provider logging includes `provider`
- startup wiring in `app/main.py` respects `LLM_PROVIDER`
- API debug payload uses `stage="llm_summarize"` for summarize failures
- `tests/test_trigger_crawl.py` is updated to assert the provider-neutral `llm_summarize` stage

Suggested test placement:

- `tests/test_llm_factory.py` for provider selection and config errors
- provider-specific tests in `tests/test_openai_service.py` and `tests/test_gemini_service.py` if needed
- update `tests/test_news_pipeline.py` for provider field assertions in logs

## Dependencies

Use the official Google Gen AI SDK and add `google-genai` explicitly in `requirements.txt`.

The implementation should document the new provider settings in `README.md` and `.env.example`.

`README.md` should also be corrected so it no longer claims that all secrets are always required; only the active provider key is required for summarization.

## Success Criteria

This design is successful when:

- the app can run with either OpenAI or Gemini using env config only
- the pipeline code does not need provider-specific branching
- logs clearly show which provider handled summarization
- tests verify provider selection and provider-specific config errors
