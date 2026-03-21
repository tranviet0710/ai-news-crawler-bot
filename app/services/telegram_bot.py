from __future__ import annotations

import html
from dataclasses import dataclass

import requests

from app.services.schemas import NewsItem, SummarizedNews


@dataclass(frozen=True)
class CommandPayload:
    command: str
    chat_id: str
    chat_type: str
    username: str | None
    first_name: str | None


@dataclass(frozen=True)
class DeliveryError:
    message: str
    is_permanent: bool


class TelegramDeliveryException(RuntimeError):
    def __init__(self, message: str, *, is_permanent: bool):
        super().__init__(message)
        self.is_permanent = is_permanent


class TelegramBot:
    def __init__(self, bot_token: str, chat_id: str = "", timeout: int = 15):
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
            f"Nguồn: {source}\n"
            f'<a href="{url}">Đọc chi tiết</a>'
        )

    def build_welcome_message(self) -> str:
        return "Chào mừng bạn. Gửi /start để đăng ký, /stop để dừng nhận tin, /status để xem trạng thái."

    def build_help_message(self) -> str:
        return "Lệnh hỗ trợ: /start, /stop, /status, /help"

    def build_stop_message(self) -> str:
        return "Bạn đã dừng nhận tin AI mới nhất."

    def build_status_message(self, is_active: bool) -> str:
        return "Bạn đang đăng ký nhận tin AI mới nhất." if is_active else "Bạn chưa đăng ký nhận tin AI mới nhất. Gửi /start để bắt đầu."

    def build_private_chat_only_message(self) -> str:
        return "Hãy nhắn tin riêng cho bot và gửi /start để đăng ký."

    def parse_command(self, update: dict[str, object]) -> CommandPayload | None:
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        text = message.get("text")
        chat = message.get("chat")
        sender = message.get("from") or {}
        if not isinstance(text, str) or not isinstance(chat, dict):
            return None
        chat_id = str(chat.get("id", ""))
        chat_type = str(chat.get("type", ""))
        if not text.startswith("/"):
            return None
        if chat_type != "private":
            return CommandPayload(
                command="unsupported_chat",
                chat_id=chat_id,
                chat_type=chat_type,
                username=sender.get("username") if isinstance(sender, dict) else None,
                first_name=sender.get("first_name") if isinstance(sender, dict) else None,
            )
        command = text.split()[0].lstrip("/").split("@", 1)[0].lower()
        return CommandPayload(
            command=command,
            chat_id=chat_id,
            chat_type=chat_type,
            username=sender.get("username") if isinstance(sender, dict) else None,
            first_name=sender.get("first_name") if isinstance(sender, dict) else None,
        )

    def send_text(self, chat_id: str, text: str) -> None:
        self._send_payload(chat_id=chat_id, text=text)

    def send_news(self, chat_id: str, item: NewsItem, ai_summary: SummarizedNews) -> None:
        self._send_payload(chat_id=chat_id, text=self.build_message(item, ai_summary))

    def send(self, item: NewsItem, ai_summary: SummarizedNews) -> None:
        if not self.chat_id:
            raise RuntimeError("Telegram chat id is not configured")
        self.send_news(self.chat_id, item, ai_summary)

    def classify_delivery_error(self, exc: Exception) -> DeliveryError:
        if isinstance(exc, TelegramDeliveryException):
            return DeliveryError(message=str(exc), is_permanent=exc.is_permanent)
        if isinstance(exc, requests.Timeout):
            return DeliveryError(message=str(exc), is_permanent=False)
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            description = exc.response.text or str(exc)
            permanent = exc.response.status_code in {400, 403}
            return DeliveryError(message=description, is_permanent=permanent)
        return DeliveryError(message=str(exc), is_permanent=False)

    def _send_payload(self, *, chat_id: str, text: str) -> None:
        if not self.bot_token or not chat_id:
            raise RuntimeError("Telegram bot token or chat id is not configured")
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            classified = self.classify_delivery_error(exc)
            raise TelegramDeliveryException(classified.message, is_permanent=classified.is_permanent) from exc
