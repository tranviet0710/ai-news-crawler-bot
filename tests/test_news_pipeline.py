import logging
from datetime import datetime, timezone

from app.services.pipeline import NewsPipeline
from app.services.schemas import NewsItem, SummarizedNews


class StubCrawler:
    def fetch_recent_entries(self, *, run_id):
        return [
            NewsItem(
                title="Existing item",
                url="https://example.com/existing",
                summary="Already sent",
                published_at=datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),
                source="Example",
            ),
            NewsItem(
                title="Important launch",
                url="https://example.com/launch",
                summary="New coding model",
                published_at=datetime(2026, 3, 16, 10, 30, tzinfo=timezone.utc),
                source="Example",
            ),
            NewsItem(
                title="Generic post",
                url="https://example.com/skip",
                summary="Marketing fluff",
                published_at=datetime(2026, 3, 16, 10, 45, tzinfo=timezone.utc),
                source="Example",
            ),
        ]


class StubRepository:
    def __init__(self):
        self.saved = []
        self.deleted = []

    def exists(self, url):
        return url == "https://example.com/existing"

    def save(self, item, ai_summary):
        self.saved.append((item, ai_summary))

    def delete(self, url):
        self.deleted.append(url)
        self.saved = [entry for entry in self.saved if entry[0].url != url]


class SaveFailingRepository(StubRepository):
    def save(self, item, ai_summary):
        raise RuntimeError("supabase unavailable")


class ExistsFailingRepository(StubRepository):
    def exists(self, url):
        raise RuntimeError("SUPABASE_KEY=top-secret")


class StubSummarizer:
    provider = "groq"
    api_key = "groq-key"

    def summarize(self, item):
        if item.url.endswith("skip"):
            return None
        return SummarizedNews(
            summary="Tom tat ngan gon",
            rationale="Relevant AI release",
        )


class FailingSummarizer:
    provider = "groq"
    api_key = "secret-key"

    def summarize(self, item):
        if item.url.endswith("skip"):
            return None
        raise RuntimeError("GROQ_API_KEY=secret-key")


class StubTelegram:
    def __init__(self):
        self.messages = []

    def send(self, item, ai_summary):
        self.messages.append((item, ai_summary))


class FailingTelegram:
    def __init__(self):
        self.calls = 0

    def send(self, item, ai_summary):
        self.calls += 1
        raise RuntimeError("telegram unavailable")


def test_news_pipeline_sends_only_new_relevant_news():
    repository = StubRepository()
    telegram = StubTelegram()
    pipeline = NewsPipeline(
        crawler=StubCrawler(),
        repository=repository,
        summarizer=StubSummarizer(),
        telegram=telegram,
    )

    result = pipeline.run(run_id="run-123")

    assert result.total_fetched == 3
    assert result.skipped_existing == 1
    assert result.skipped_irrelevant == 1
    assert result.sent == 1
    assert result.errors == []
    assert len(repository.saved) == 1
    assert len(telegram.messages) == 1
    assert telegram.messages[0][0].title == "Important launch"


def test_news_pipeline_does_not_save_when_delivery_fails():
    repository = StubRepository()
    pipeline = NewsPipeline(
        crawler=StubCrawler(),
        repository=repository,
        summarizer=StubSummarizer(),
        telegram=FailingTelegram(),
    )

    result = pipeline.run(run_id="run-123")

    assert result.sent == 0
    assert result.failed_delivery == 1
    assert repository.saved == []
    assert repository.deleted == ["https://example.com/launch"]
    assert result.errors[0]["stage"] == "telegram_send"


def test_news_pipeline_skips_send_when_persistence_fails():
    telegram = StubTelegram()
    pipeline = NewsPipeline(
        crawler=StubCrawler(),
        repository=SaveFailingRepository(),
        summarizer=StubSummarizer(),
        telegram=telegram,
    )

    result = pipeline.run(run_id="run-123")

    assert result.sent == 0
    assert result.failed_processing == 1
    assert telegram.messages == []
    assert result.errors[0]["stage"] == "supabase_save"


def test_pipeline_records_sanitized_groq_error(caplog):
    caplog.set_level(logging.WARNING)
    pipeline = NewsPipeline(
        crawler=StubCrawler(),
        repository=StubRepository(),
        summarizer=FailingSummarizer(),
        telegram=StubTelegram(),
    )

    result = pipeline.run(run_id="run-123")

    assert result.failed_processing == 1
    assert result.errors[0]["stage"] == "llm_summarize"
    assert result.errors[0]["provider"] == "groq"
    assert "secret-key" not in str(result.errors[0]["message"])
    assert "OPENAI_API_KEY" not in str(result.errors[0]["message"])
    assert any(
        getattr(record, "event", None) == "llm_summarize_failed"
        and getattr(record, "provider", None) == "groq"
        for record in caplog.records
    )


def test_pipeline_records_exists_failure_as_recoverable_error(caplog):
    caplog.set_level(logging.WARNING)
    pipeline = NewsPipeline(
        crawler=StubCrawler(),
        repository=ExistsFailingRepository(),
        summarizer=StubSummarizer(),
        telegram=StubTelegram(),
    )

    result = pipeline.run(run_id="run-123")

    assert result.failed_processing == 3
    assert result.errors[0]["stage"] == "supabase_exists"
    assert result.errors[0]["recoverable"] is True
    assert "top-secret" not in str(result.errors[0]["message"])
    assert any(getattr(record, "event", None) == "supabase_exists_failed" for record in caplog.records)


def test_pipeline_caps_errors_at_ten_in_encounter_order():
    class ManyItemsCrawler:
        def fetch_recent_entries(self, *, run_id):
            return [
                NewsItem(
                    title=f"Item {index}",
                    url=f"https://example.com/item-{index}",
                    summary="summary",
                    published_at=datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),
                    source="Example",
                )
                for index in range(12)
            ]

    pipeline = NewsPipeline(
        crawler=ManyItemsCrawler(),
        repository=ExistsFailingRepository(),
        summarizer=StubSummarizer(),
        telegram=StubTelegram(),
    )

    result = pipeline.run(run_id="run-123")

    assert len(result.errors) == 10
    assert result.suppressed_error_count == 2
    assert result.errors[0]["url"] == "https://example.com/item-0"
    assert result.errors[-1]["url"] == "https://example.com/item-9"
