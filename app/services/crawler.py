from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Iterable, Protocol
from xml.etree import ElementTree

import requests

from app.core.logging import get_logger, sanitize_message
from app.services.schemas import NewsItem


@dataclass(frozen=True)
class FeedEntry:
    title: str
    url: str
    summary: str
    published_at: datetime
    source: str


class NewsCrawler(Protocol):
    def fetch_recent_entries(self, *, run_id: str) -> list[NewsItem]: ...


def extract_recent_entries(rss_content: str, now: datetime, lookback_hours: int) -> list[FeedEntry]:
    root = ElementTree.fromstring(rss_content)
    cutoff = now - timedelta(hours=lookback_hours)
    items: list[FeedEntry] = []

    for node in root.findall("./channel/item"):
        published_text = (node.findtext("pubDate") or "").strip()
        if not published_text:
            continue

        published_at = parsedate_to_datetime(published_text)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        published_at = published_at.astimezone(timezone.utc)

        if published_at < cutoff:
            continue

        items.append(
            FeedEntry(
                title=(node.findtext("title") or "").strip(),
                url=(node.findtext("link") or "").strip(),
                summary=(node.findtext("description") or "").strip(),
                published_at=published_at,
                source=(root.findtext("./channel/title") or "RSS Feed").strip(),
            )
        )

    return items


class RSSCrawler:
    def __init__(
        self,
        sources: Iterable[str],
        lookback_hours: int = 2,
        timeout: int = 20,
        now_provider=None,
    ):
        self.sources = list(sources)
        self.lookback_hours = lookback_hours
        self.timeout = timeout
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.logger = get_logger("crawler.rss")

    def fetch_recent_entries(self, *, run_id: str) -> list[NewsItem]:
        now = self.now_provider()
        collected: list[NewsItem] = []

        for source in self.sources:
            self.logger.info("source_fetch_started", extra={"event": "source_fetch_started", "run_id": run_id, "source_id": source, "source_type": "rss"})
            try:
                response = requests.get(source, timeout=self.timeout)
                response.raise_for_status()
                entries = extract_recent_entries(
                    response.text,
                    now=now,
                    lookback_hours=self.lookback_hours,
                )
            except Exception as exc:
                self.logger.warning(
                    "source_fetch_failed",
                    extra={
                        "event": "source_fetch_failed",
                        "run_id": run_id,
                        "source_id": source,
                        "source_type": "rss",
                        "error_type": type(exc).__name__,
                        "error_message": sanitize_message(str(exc)),
                    },
                )
                continue
            self.logger.info(
                "source_fetch_succeeded",
                extra={
                    "event": "source_fetch_succeeded",
                    "run_id": run_id,
                    "source_id": source,
                    "source_type": "rss",
                    "items_collected": len(entries),
                },
            )
            collected.extend(
                NewsItem(
                    title=entry.title,
                    url=entry.url,
                    summary=entry.summary,
                    published_at=entry.published_at,
                    source=entry.source,
                )
                for entry in entries
            )

        return collected


class HackerNewsCrawler:
    def __init__(
        self,
        top_stories_url: str = "https://hacker-news.firebaseio.com/v0/topstories.json",
        item_url_template: str = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
        lookback_hours: int = 2,
        timeout: int = 20,
        max_items: int = 20,
        now_provider=None,
        keywords: Iterable[str] | None = None,
    ):
        self.top_stories_url = top_stories_url
        self.item_url_template = item_url_template
        self.lookback_hours = lookback_hours
        self.timeout = timeout
        self.max_items = max_items
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.logger = get_logger("crawler.hackernews")
        self.keywords = tuple(
            keywords
            or (
                "agent",
                "llm",
                "model",
                "openai",
                "anthropic",
                "google",
                "claude",
                "gemini",
                "machine learning",
                "artificial intelligence",
            )
        )

    def fetch_recent_entries(self, *, run_id: str) -> list[NewsItem]:
        now = self.now_provider()
        cutoff = now - timedelta(hours=self.lookback_hours)
        self.logger.info("source_fetch_started", extra={"event": "source_fetch_started", "run_id": run_id, "source_id": "hackernews", "source_type": "hackernews"})
        try:
            response = requests.get(self.top_stories_url, timeout=self.timeout)
            response.raise_for_status()
            story_ids = response.json()[: self.max_items]
        except Exception as exc:
            self.logger.warning(
                "source_fetch_failed",
                extra={
                    "event": "source_fetch_failed",
                    "run_id": run_id,
                    "source_id": "hackernews",
                    "source_type": "hackernews",
                    "error_type": type(exc).__name__,
                    "error_message": sanitize_message(str(exc)),
                },
            )
            return []

        items: list[NewsItem] = []
        for story_id in story_ids:
            try:
                item_response = requests.get(
                    self.item_url_template.format(item_id=story_id),
                    timeout=self.timeout,
                )
                item_response.raise_for_status()
                payload = item_response.json()
            except Exception:
                continue

            title = (payload.get("title") or "").strip()
            url = (payload.get("url") or f"https://news.ycombinator.com/item?id={story_id}").strip()
            published_at = datetime.fromtimestamp(payload.get("time", 0), tz=timezone.utc)
            if published_at < cutoff:
                continue
            if not self._is_ai_related(title):
                continue

            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    summary=(payload.get("text") or "").strip(),
                    published_at=published_at,
                    source="Hacker News",
                )
            )

        self.logger.info(
            "source_fetch_succeeded",
            extra={
                "event": "source_fetch_succeeded",
                "run_id": run_id,
                "source_id": "hackernews",
                "source_type": "hackernews",
                "items_collected": len(items),
            },
        )
        return items

    def _is_ai_related(self, title: str) -> bool:
        lowered = title.lower()
        if re.search(r"\bai\b", lowered):
            return True
        return any(keyword in lowered for keyword in self.keywords)


class MultiSourceCrawler:
    def __init__(self, crawlers: Iterable[NewsCrawler]):
        self.crawlers: list[NewsCrawler] = list(crawlers)

    def fetch_recent_entries(self, *, run_id: str) -> list[NewsItem]:
        items: list[NewsItem] = []
        for crawler in self.crawlers:
            try:
                items.extend(crawler.fetch_recent_entries(run_id=run_id))
            except Exception:
                continue
        return items
