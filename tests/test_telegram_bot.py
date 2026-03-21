from datetime import datetime, timezone
from typing import cast

import pytest
import requests

from app.services.schemas import NewsItem, SummarizedNews
from app.services.telegram_bot import CommandPayload, TelegramBot


@pytest.fixture
def news_item():
    return NewsItem(
        title="Important <launch>",
        url="https://example.com/post",
        summary="Summary",
        published_at=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
        source="Example",
    )


@pytest.fixture
def ai_summary():
    return SummarizedNews(summary="Tom tat", rationale="Relevant")


def test_build_message_formats_html_news(news_item, ai_summary):
    bot = TelegramBot(bot_token="token")

    text = bot.build_message(news_item, ai_summary)

    assert "<b>Important &lt;launch&gt;</b>" in text
    assert "Nguồn: Example" in text
    assert "Đọc chi tiết" in text


def test_build_copy_messages_use_vietnamese_accents():
    bot = TelegramBot(bot_token="token")

    assert bot.build_welcome_message() == "Chào mừng bạn. Gửi /start để đăng ký, /stop để dừng nhận tin, /status để xem trạng thái."
    assert bot.build_help_message() == "Lệnh hỗ trợ: /start, /stop, /status, /help"
    assert bot.build_status_message(True) == "Bạn đang đăng ký nhận tin AI mới nhất."
    assert bot.build_status_message(False) == "Bạn chưa đăng ký nhận tin AI mới nhất. Gửi /start để bắt đầu."
    assert bot.build_private_chat_only_message() == "Hãy nhắn tin riêng cho bot và gửi /start để đăng ký."


def test_parse_start_command_from_private_chat():
    bot = TelegramBot(bot_token="token")
    update = {
        "message": {
            "text": "/start",
            "chat": {"id": 42, "type": "private"},
            "from": {"username": "viet", "first_name": "Viet"},
        }
    }

    result = cast(CommandPayload | None, bot.parse_command(cast(dict[str, object], update)))

    assert result is not None
    assert result.command == "start"
    assert result.chat_id == "42"
    assert result.chat_type == "private"


def test_parse_group_chat_returns_guidance_action():
    bot = TelegramBot(bot_token="token")
    update = {
        "message": {
            "text": "/start",
            "chat": {"id": -100, "type": "group"},
            "from": {"username": "viet", "first_name": "Viet"},
        }
    }

    result = cast(CommandPayload | None, bot.parse_command(cast(dict[str, object], update)))

    assert result is not None
    assert result.command == "unsupported_chat"
    assert result.chat_type == "group"


def test_classify_delivery_error_marks_blocked_user_as_permanent():
    bot = TelegramBot(bot_token="token")
    response = requests.Response()
    response.status_code = 403
    response._content = b'{"ok":false,"description":"Forbidden: bot was blocked by the user"}'
    exc = requests.HTTPError("403 Client Error", response=response)

    delivery_error = bot.classify_delivery_error(exc)

    assert delivery_error.is_permanent is True
    assert "blocked" in delivery_error.message.lower()


def test_classify_delivery_error_marks_timeout_as_transient():
    bot = TelegramBot(bot_token="token")

    delivery_error = bot.classify_delivery_error(requests.Timeout("timeout"))

    assert delivery_error.is_permanent is False
    assert delivery_error.message == "timeout"
