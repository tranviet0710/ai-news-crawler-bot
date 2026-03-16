from datetime import datetime, timedelta, timezone

from app.services.crawler import extract_recent_entries


RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>AI News</title>
    <item>
      <title>Fresh launch</title>
      <link>https://example.com/fresh</link>
      <description>New model release</description>
      <pubDate>Mon, 16 Mar 2026 10:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Old launch</title>
      <link>https://example.com/old</link>
      <description>Old news</description>
      <pubDate>Mon, 16 Mar 2026 07:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_extract_recent_entries_filters_old_items():
    now = datetime(2026, 3, 16, 11, 0, tzinfo=timezone.utc)

    items = extract_recent_entries(RSS_FEED, now=now, lookback_hours=2)

    assert len(items) == 1
    assert items[0].title == "Fresh launch"
    assert items[0].url == "https://example.com/fresh"
    assert items[0].published_at == now - timedelta(minutes=30)
