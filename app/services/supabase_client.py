from __future__ import annotations

from app.services.schemas import NewsItem, SummarizedNews


class SupabaseNewsRepository:
    def __init__(self, url: str, key: str, table_name: str = "processed_news"):
        self.url = url
        self.key = key
        self.table_name = table_name
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.url or not self.key:
                raise RuntimeError("Supabase credentials are not configured")
            try:
                from supabase import create_client
            except ImportError as exc:
                raise RuntimeError("supabase package is not installed") from exc
            self._client = create_client(self.url, self.key)
        return self._client

    def exists(self, url: str) -> bool:
        response = (
            self.client.table(self.table_name)
            .select("id")
            .eq("url", url)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def save(self, item: NewsItem, ai_summary: SummarizedNews) -> None:
        self.client.table(self.table_name).insert(
            {
                "url": item.url,
                "title": item.title,
                "published_at": item.published_at.isoformat(),
                "summary": ai_summary.summary,
                "source": item.source,
            }
        ).execute()

    def delete(self, url: str) -> None:
        self.client.table(self.table_name).delete().eq("url", url).execute()
