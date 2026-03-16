from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    summary: str
    published_at: datetime
    source: str


@dataclass(frozen=True)
class SummarizedNews:
    summary: str
    rationale: str
