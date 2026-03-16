import logging
from datetime import datetime, timezone

from app.services.crawler import HackerNewsCrawler


class StubResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_hackernews_crawler_keeps_recent_ai_posts(monkeypatch):
    now = datetime(2026, 3, 16, 11, 0, tzinfo=timezone.utc)

    def fake_get(url, timeout):
        if url.endswith("/topstories.json"):
            return StubResponse([1, 2, 3])
        if url.endswith("/item/1.json"):
            return StubResponse(
                {
                    "title": "New AI coding agent ships",
                    "url": "https://example.com/agent",
                    "time": int(datetime(2026, 3, 16, 10, 40, tzinfo=timezone.utc).timestamp()),
                }
            )
        if url.endswith("/item/2.json"):
            return StubResponse(
                {
                    "title": "Database tuning guide",
                    "url": "https://example.com/db",
                    "time": int(datetime(2026, 3, 16, 10, 30, tzinfo=timezone.utc).timestamp()),
                }
            )
        return StubResponse(
            {
                "title": "Old AI launch",
                "url": "https://example.com/old-ai",
                "time": int(datetime(2026, 3, 16, 6, 0, tzinfo=timezone.utc).timestamp()),
            }
        )

    monkeypatch.setattr("app.services.crawler.requests.get", fake_get)

    crawler = HackerNewsCrawler(now_provider=lambda: now)

    items = crawler.fetch_recent_entries(run_id="run-123")

    assert len(items) == 1
    assert items[0].title == "New AI coding agent ships"
    assert items[0].source == "Hacker News"


def test_hackernews_crawler_logs_topstories_failure(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)

    def fake_get(url, timeout):
        raise RuntimeError("token=hn-secret")

    monkeypatch.setattr("app.services.crawler.requests.get", fake_get)

    crawler = HackerNewsCrawler()
    items = crawler.fetch_recent_entries(run_id="run-123")

    assert items == []
    assert any(
        getattr(record, "event", None) == "source_fetch_failed"
        and getattr(record, "source_id", None) == "hackernews"
        for record in caplog.records
    )
