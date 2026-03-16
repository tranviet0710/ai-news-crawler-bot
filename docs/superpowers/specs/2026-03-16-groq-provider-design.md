# Groq Provider Design For AI News Crawler

## Goal

Replace the current OpenAI-backed summarization path with a first-class Groq provider so the app can run with `LLM_PROVIDER=groq` using `GROQ_API_KEY`.

## Scope

This design covers:

- adding `groq` as a supported `LLM_PROVIDER` value
- switching the active OpenAI-specific summarizer path to Groq credentials and naming
- updating config, runtime wiring, tests, and docs to reflect Groq as the provider
- preserving the existing summarizer interface used by the pipeline

This design does not cover:

- keeping OpenAI as a supported provider in parallel
- runtime fallback between providers
- per-request provider selection
- changes to Telegram, Supabase, crawler, or prompt behavior beyond provider naming

## Current State

- The app currently supports `openai` and `gemini` provider values.
- OpenAI is wired through `OPENAI_API_KEY`, `OPENAI_MODEL`, `OpenAISummarizer`, and factory selection in `app/services/llm_factory.py`.
- README and env examples instruct users to configure OpenAI or Gemini credentials.

## Recommended Approach

Introduce Groq as a first-class provider and remove OpenAI from active provider selection.

The implementation should keep the existing pipeline contract unchanged: startup chooses one summarizer implementation from `LLM_PROVIDER`, and the pipeline continues calling `summarize(item)` without provider-specific branching.

## Architecture

### Provider Interface

Keep the current summarizer shape:

- `summarize(item: NewsItem) -> SummarizedNews | None`
- `provider: str`
- provider-specific API key and model stored on the summarizer instance

Behavior should remain unchanged:

- return `None` for skipped or irrelevant items
- return `SummarizedNews` for accepted items
- raise a runtime error for missing active-provider config or upstream API failures

### Service Layout

Recommended structure:

- add `app/services/groq_service.py` for `GroqSummarizer`
- keep `app/services/gemini_service.py` unchanged
- update `app/services/llm_factory.py` to select `groq` or `gemini`
- keep using `app/services/llm_prompt.py` for the shared prompt

This isolates provider-specific request code and avoids carrying OpenAI naming forward when Groq is the intended backend.

OpenAI service handling rule:

- replace `app/services/openai_service.py` with `app/services/groq_service.py` so there is no dead OpenAI runtime service left behind
- no code path should require `OPENAI_API_KEY` after the change

### Configuration

Update `app/core/config.py` to expose fields for:

- `LLM_PROVIDER`
- `GROQ_API_KEY`
- `GROQ_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`

Defaults:

- `LLM_PROVIDER=groq`
- `GROQ_MODEL=llama-3.1-8b-instant`
- `GEMINI_MODEL` can remain unchanged

Validation ownership:

- `app/core/config.py` should only expose fields and defaults
- `app/services/llm_factory.py` is the single place that validates `LLM_PROVIDER`, active-provider API key presence, and active-provider model presence
- app startup should continue calling the factory so invalid configuration fails fast during `create_app()`

Validation rules:

- `LLM_PROVIDER` values are validated only in `app/services/llm_factory.py`, where the supported values are `groq` and `gemini`
- if `LLM_PROVIDER=groq`, `GROQ_API_KEY` is required
- if `LLM_PROVIDER=groq`, `GROQ_MODEL` must be non-empty after config loading
- if `LLM_PROVIDER=gemini`, `GEMINI_API_KEY` is required
- if `LLM_PROVIDER=gemini`, `GEMINI_MODEL` must be non-empty after config loading
- invalid provider values should fail fast during app startup via the summarizer factory
- inactive-provider credentials remain optional
- remove `OPENAI_API_KEY` and `OPENAI_MODEL` from settings, docs, and env examples rather than leaving them as ignored legacy fields

### Runtime Wiring

`app/main.py` should continue to construct the summarizer through `build_summarizer(settings)`.

Factory behavior should become:

- `groq` => `GroqSummarizer`
- `gemini` => `GeminiSummarizer`
- any other provider => clear runtime error mentioning supported values

Startup validation should still happen when the app is created so config problems fail early.

### Provider Implementation

Groq should be implemented through the existing OpenAI-compatible SDK pattern using the existing `openai` Python package, configured explicitly for Groq's OpenAI-compatible API.

Implementation rule:

- use exactly one Groq client path in code and tests: the existing `openai` package
- do not introduce a second dedicated Groq SDK for this change
- configure the client with `api_key=GROQ_API_KEY` and `base_url="https://api.groq.com/openai/v1"` so requests are sent to Groq rather than OpenAI defaults
- keep using the existing `responses.create(...)` request shape so request construction and response parsing stay aligned with the current code

Expected request behavior:

- initialize the client with `GROQ_API_KEY`
- initialize it with Groq's OpenAI-compatible base URL `https://api.groq.com/openai/v1`
- send the existing shared system/user prompt content
- read text output and map `SKIP` to `None`
- otherwise return `SummarizedNews`

Error messages should mention Groq-specific env vars, for example:

- `GROQ_API_KEY is not configured`
- `GROQ_MODEL is not configured`

### Logging And Error Surface

Summarizer-facing provider metadata should report `provider="groq"` when Groq is active.

Naming rule:

- pipeline and API-visible summarize stages should use provider-neutral `llm_*` names
- the `provider` field should carry `groq` or `gemini`
- provider-specific internal request details may mention Groq explicitly, but operator-facing config errors and debug payloads must never mention `OPENAI_API_KEY`

The main rule is that user-visible failures should no longer instruct operators to configure OpenAI credentials when Groq is the active provider.

## API And Pipeline Impact

No API shape change is required.

The pipeline should continue to accept one summarizer object and remain unaware of whether Groq or Gemini is active.

## Testing Strategy

Add or update tests for:

- factory returns `GroqSummarizer` when `LLM_PROVIDER=groq`
- factory returns the existing Gemini summarizer when `LLM_PROVIDER=gemini`
- invalid `LLM_PROVIDER` raises a clear error mentioning `groq` and `gemini`
- missing `GROQ_API_KEY` raises the correct config error
- overriding `GROQ_MODEL` with an empty value raises the correct config error
- inactive-provider credentials are not required
- Groq summarizer maps `SKIP` to `None`
- app startup wiring respects `LLM_PROVIDER=groq`
- any pipeline or API debug assertions that currently reference `OPENAI_API_KEY` or `openai_*` are updated for the new provider behavior

Suggested test placement:

- `tests/test_llm_factory.py` for provider selection and config errors
- a new `tests/test_groq_service.py` for Groq-specific summarize behavior if provider services are tested directly
- updates in `tests/test_news_pipeline.py` and `tests/test_trigger_crawl.py` where OpenAI-specific failure text is asserted

OpenAI test handling rule:

- rewrite current OpenAI provider-selection tests to Groq equivalents
- delete direct OpenAI runtime tests that only cover the removed provider path
- keep no legacy OpenAI assertions once the runtime provider is removed

## Dependencies

The implementation should continue using the existing `openai` Python package for the Groq path, with explicit Groq-compatible base URL configuration.

README and `.env.example` should be updated to describe Groq and Gemini as the supported providers.

`OPENAI_API_KEY` and `OPENAI_MODEL` should be removed from docs and examples, not left behind as stale config.

## Migration And Rollout

This change is a deliberate config migration.

Migration rules:

- existing deployments must replace `OPENAI_API_KEY` with `GROQ_API_KEY`
- existing deployments must replace `OPENAI_MODEL` with `GROQ_MODEL` if they override the model
- deployments that relied on the default `LLM_PROVIDER` should expect the new default to become `groq`
- startup should fail fast with a Groq-specific config error if an environment has not been migrated

There is no compatibility alias for legacy `OPENAI_*` variables in this design. The goal is a clean switch, not a mixed transition layer.

## Success Criteria

This design is successful when:

- the app runs with `LLM_PROVIDER=groq` using `GROQ_API_KEY`
- OpenAI credentials are no longer required or documented for active summarization
- Gemini support continues to work unchanged
- tests and runtime errors clearly reference Groq where that provider is active
- no supported runtime path, docs page, env example, or test suite entry still treats OpenAI as an active provider
