from datetime import datetime, timezone
import sys
from types import SimpleNamespace

import pytest

from app.services.groq_service import GroqSummarizer
from app.services.llm_prompt import PROMPT, build_news_prompt
from app.services.schemas import NewsItem


ITEM = NewsItem(
    title="Important launch",
    url="https://example.com/launch",
    summary="New coding model",
    published_at=datetime(2026, 3, 16, 10, 30, tzinfo=timezone.utc),
    source="Example",
)


class StubResponses:
    def __init__(self, output_text, capture=None):
        self.output_text = output_text
        self.capture = capture

    def create(self, **kwargs):
        if self.capture is not None:
            self.capture.update(kwargs)
        return type("StubResponse", (), {"output_text": self.output_text})()


class StubClient:
    def __init__(self, output_text, capture=None):
        self.responses = StubResponses(output_text, capture)


def test_groq_summarizer_returns_none_for_skip(monkeypatch):
    monkeypatch.setattr(
        "app.services.groq_service.build_groq_client",
        lambda api_key: StubClient("SKIP"),
    )
    summarizer = GroqSummarizer(api_key="groq-key", model="llama-3.1-8b-instant")

    assert summarizer.summarize(ITEM) is None


def test_groq_summarizer_returns_summary_for_text_response(monkeypatch):
    monkeypatch.setattr(
        "app.services.groq_service.build_groq_client",
        lambda api_key: StubClient("Tom tat ngan gon"),
    )
    summarizer = GroqSummarizer(api_key="groq-key", model="llama-3.1-8b-instant")

    result = summarizer.summarize(ITEM)

    assert result is not None
    assert result.summary == "Tom tat ngan gon"
    assert result.rationale == "Accepted by Groq filter"


def test_groq_summarizer_rejects_missing_api_key():
    summarizer = GroqSummarizer(api_key="", model="llama-3.1-8b-instant")

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        summarizer.summarize(ITEM)


def test_groq_summarizer_rejects_missing_model():
    summarizer = GroqSummarizer(api_key="groq-key", model="")

    with pytest.raises(RuntimeError, match="GROQ_MODEL"):
        summarizer.summarize(ITEM)


def test_groq_summarizer_rejects_whitespace_only_values():
    summarizer = GroqSummarizer(api_key="   ", model="   ")

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        summarizer.summarize(ITEM)


def test_build_groq_client_uses_groq_base_url(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    from app.services.groq_service import build_groq_client

    build_groq_client("groq-key")

    assert captured == {
        "api_key": "groq-key",
        "base_url": "https://api.groq.com/openai/v1",
    }


def test_groq_summarizer_sends_expected_prompt_shape(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.services.groq_service.build_groq_client",
        lambda api_key: StubClient("Tom tat ngan gon", capture=captured),
    )
    summarizer = GroqSummarizer(api_key="groq-key", model="llama-3.1-8b-instant")

    summarizer.summarize(ITEM)

    assert captured == {
        "model": "llama-3.1-8b-instant",
        "input": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": build_news_prompt(ITEM.title, ITEM.source, ITEM.summary, ITEM.url)},
        ],
    }


def test_groq_summarizer_raises_for_empty_text(monkeypatch):
    monkeypatch.setattr(
        "app.services.groq_service.build_groq_client",
        lambda api_key: StubClient(""),
    )
    summarizer = GroqSummarizer(api_key="groq-key", model="llama-3.1-8b-instant")

    with pytest.raises(RuntimeError, match="Groq"):
        summarizer.summarize(ITEM)
