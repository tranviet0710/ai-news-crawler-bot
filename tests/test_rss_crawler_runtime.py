import logging
from datetime import datetime, timezone

import requests

from app.services.crawler import RSSCrawler


class StubResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_rss_crawler_continues_when_one_source_fails(monkeypatch):
    fresh_feed = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Working Feed</title>
        <item>
          <title>Fresh launch</title>
          <link>https://example.com/fresh</link>
          <description>New model release</description>
          <pubDate>Mon, 16 Mar 2026 10:30:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """

    def fake_get(url, timeout):
        if "bad" in url:
            raise requests.RequestException("boom")
        return StubResponse(fresh_feed)

    monkeypatch.setattr("app.services.crawler.requests.get", fake_get)
    crawler = RSSCrawler(
        sources=["https://bad.example.com/rss", "https://good.example.com/rss"],
        lookback_hours=2,
        now_provider=lambda: datetime(2026, 3, 16, 11, 0, tzinfo=timezone.utc),
    )

    items = crawler.fetch_recent_entries(run_id="run-123")

    assert len(items) == 1
    assert items[0].source == "Working Feed"


def test_rss_crawler_logs_source_failure(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)

    def fake_get(url, timeout):
        raise RuntimeError("Bearer abc123")

    monkeypatch.setattr("app.services.crawler.requests.get", fake_get)
    crawler = RSSCrawler(sources=["https://example.com/feed.xml"])

    items = crawler.fetch_recent_entries(run_id="run-123")

    assert items == []
    assert any(getattr(record, "event", None) == "source_fetch_failed" for record in caplog.records)
