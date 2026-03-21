from __future__ import annotations

from datetime import datetime, timezone

from app.services.schemas import NewsItem, SummarizedNews


class SupabaseNewsRepository:
    def __init__(self, url: str, key: str, table_name: str = "processed_news"):
        self.url = url
        self.key = key
        self.table_name = table_name
        self.subscribers_table = "telegram_subscribers"
        self.deliveries_table = "telegram_deliveries"
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

    def upsert_subscriber(self, chat_id: str, username: str | None, first_name: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.client.table(self.subscribers_table).upsert(
            {
                "chat_id": chat_id,
                "username": username,
                "first_name": first_name,
                "is_active": True,
                "subscribed_at": now,
                "unsubscribed_at": None,
                "updated_at": now,
            },
            on_conflict="chat_id",
        ).execute()

    def deactivate_subscriber(self, chat_id: str) -> None:
        self.client.table(self.subscribers_table).update(
            {
                "is_active": False,
                "unsubscribed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("chat_id", chat_id).execute()

    def deactivate_subscriber_for_delivery_error(self, chat_id: str, error_message: str) -> None:
        self.client.table(self.subscribers_table).update(
            {
                "is_active": False,
                "delivery_error": error_message,
                "unsubscribed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("chat_id", chat_id).execute()

    def get_subscriber(self, chat_id: str) -> dict[str, object] | None:
        response = self.client.table(self.subscribers_table).select("*").eq("chat_id", chat_id).limit(1).execute()
        if not response.data:
            return None
        return response.data[0]

    def list_active_subscribers(self) -> list[dict[str, object]]:
        response = self.client.table(self.subscribers_table).select("*").eq("is_active", True).execute()
        return list(response.data or [])

    def create_delivery_attempt(self, news_url: str, chat_id: str) -> bool:
        existing = (
            self.client.table(self.deliveries_table)
            .select("status")
            .eq("news_url", news_url)
            .eq("chat_id", chat_id)
            .limit(1)
            .execute()
        )
        if existing.data and existing.data[0].get("status") == "sent":
            return False

        self.client.table(self.deliveries_table).upsert(
            {
                "news_url": news_url,
                "chat_id": chat_id,
                "status": "pending",
                "error": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="news_url,chat_id",
        ).execute()
        return True

    def mark_delivery_sent(self, news_url: str, chat_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.client.table(self.deliveries_table).update(
            {
                "status": "sent",
                "delivered_at": now,
                "error": None,
                "updated_at": now,
            }
        ).eq("news_url", news_url).eq("chat_id", chat_id).execute()
        self.client.table(self.subscribers_table).update(
            {
                "last_delivery_at": now,
                "delivery_error": None,
                "updated_at": now,
            }
        ).eq("chat_id", chat_id).execute()

    def mark_delivery_failed(self, news_url: str, chat_id: str, error_message: str) -> None:
        self.client.table(self.deliveries_table).update(
            {
                "status": "failed",
                "error": error_message,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("news_url", news_url).eq("chat_id", chat_id).execute()
