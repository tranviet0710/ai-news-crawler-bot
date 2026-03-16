from datetime import datetime, timezone

from app.services.gemini_service import GeminiSummarizer
from app.services.schemas import NewsItem


ITEM = NewsItem(
    title="Important launch",
    url="https://example.com/launch",
    summary="New coding model",
    published_at=datetime(2026, 3, 16, 10, 30, tzinfo=timezone.utc),
    source="Example",
)


class StubResponse:
    def __init__(self, text):
        self.text = text


class StubModels:
    def __init__(self, response):
        self.response = response

    def generate_content(self, **kwargs):
        return self.response


class StubClient:
    def __init__(self, response):
        self.models = StubModels(response)


def test_gemini_summarizer_returns_none_for_skip(monkeypatch):
    monkeypatch.setattr("app.services.gemini_service.build_gemini_client", lambda api_key: StubClient(StubResponse("SKIP")))
    summarizer = GeminiSummarizer(api_key="gemini-key", model="gemini-1.5-flash")

    assert summarizer.summarize(ITEM) is None


def test_gemini_summarizer_returns_summary_for_text_response(monkeypatch):
    monkeypatch.setattr("app.services.gemini_service.build_gemini_client", lambda api_key: StubClient(StubResponse("Tom tat")))
    summarizer = GeminiSummarizer(api_key="gemini-key", model="gemini-1.5-flash")

    result = summarizer.summarize(ITEM)

    assert result.summary == "Tom tat"


def test_gemini_summarizer_raises_for_empty_text(monkeypatch):
    monkeypatch.setattr("app.services.gemini_service.build_gemini_client", lambda api_key: StubClient(StubResponse("")))
    summarizer = GeminiSummarizer(api_key="gemini-key", model="gemini-1.5-flash")

    try:
        summarizer.summarize(ITEM)
    except RuntimeError as exc:
        assert "Gemini" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for empty Gemini response")
