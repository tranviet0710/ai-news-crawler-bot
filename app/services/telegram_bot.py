from __future__ import annotations

import html

import requests

from app.services.schemas import NewsItem, SummarizedNews


class TelegramBot:
    def __init__(self, bot_token: str, chat_id: str, timeout: int = 15):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    def build_message(self, item: NewsItem, ai_summary: SummarizedNews) -> str:
        title = html.escape(item.title)
        summary = html.escape(ai_summary.summary)
        source = html.escape(item.source)
        url = html.escape(item.url, quote=True)
        return (
            f"<b>{title}</b>\n"
            f"{summary}\n"
            f"Nguon: {source}\n"
            f'<a href="{url}">Doc chi tiet</a>'
        )

    def send(self, item: NewsItem, ai_summary: SummarizedNews) -> None:
        if not self.bot_token or not self.chat_id:
            raise RuntimeError("Telegram bot token or chat id is not configured")

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": self.build_message(item, ai_summary),
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
