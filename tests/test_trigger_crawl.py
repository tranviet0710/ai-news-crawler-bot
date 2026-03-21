import logging
import asyncio

import httpx
from fastapi import HTTPException

from app.main import create_app


class StubPipeline:
    def __init__(self):
        self.calls = []

    def run(self, *, run_id):
        self.calls.append(run_id)
        return {
            "total_fetched": 2,
            "skipped_existing": 1,
            "skipped_irrelevant": 0,
            "sent": 1,
            "failed_delivery": 0,
            "failed_processing": 0,
            "suppressed_error_count": 0,
            "errors": [],
        }


class StubRepository:
    def __init__(self):
        self.upsert_calls = []
        self.deactivate_calls = []
        self.subscribers = {}

    def upsert_subscriber(self, chat_id, username, first_name):
        self.upsert_calls.append((chat_id, username, first_name))
        self.subscribers[chat_id] = {"chat_id": chat_id, "is_active": True}

    def deactivate_subscriber(self, chat_id):
        self.deactivate_calls.append(chat_id)
        self.subscribers[chat_id] = {"chat_id": chat_id, "is_active": False}

    def get_subscriber(self, chat_id):
        return self.subscribers.get(chat_id)


class StubTelegramBot:
    def __init__(self):
        self.replies = []

    def parse_command(self, update):
        message = update.get("message", {})
        text = message.get("text", "")
        chat = message.get("chat", {})
        sender = message.get("from", {})
        if chat.get("type") != "private":
            return type("Payload", (), {"command": "unsupported_chat", "chat_id": str(chat.get("id")), "username": sender.get("username"), "first_name": sender.get("first_name")})()
        return type("Payload", (), {"command": text.lstrip("/"), "chat_id": str(chat.get("id")), "username": sender.get("username"), "first_name": sender.get("first_name")})()

    def build_welcome_message(self):
        return "welcome"

    def build_help_message(self):
        return "help"

    def build_status_message(self, is_active):
        return "active" if is_active else "inactive"

    def build_private_chat_only_message(self):
        return "private only"

    def send_text(self, chat_id, text):
        self.replies.append((chat_id, text))


class DegradedPipeline:
    def run(self, *, run_id):
        return {
            "total_fetched": 1,
            "skipped_existing": 0,
            "skipped_irrelevant": 0,
            "sent": 0,
            "failed_delivery": 0,
            "failed_processing": 1,
            "suppressed_error_count": 0,
            "errors": [
                {
                    "stage": "llm_summarize",
                    "url": "https://example.com/post",
                    "source": "Example",
                    "provider": "groq",
                    "error_type": "RuntimeError",
                    "message": "GROQ_API_KEY is not configured",
                    "recoverable": True,
                }
            ],
        }


class HttpExceptionPipeline:
    def run(self, *, run_id):
        raise HTTPException(status_code=418, detail="teapot")


class ErrorPipeline:
    def run(self, *, run_id):
        raise RuntimeError("boom")


def test_trigger_crawl_requires_bearer_token():
    app = create_app(cron_secret="top-secret", pipeline=StubPipeline())
    response = asyncio.run(post(app))

    assert response.status_code == 401


def test_trigger_crawl_returns_202_when_authorized():
    app = create_app(cron_secret="top-secret", pipeline=StubPipeline())
    response = asyncio.run(
        post(
            app,
            headers={"Authorization": "Bearer top-secret"},
        )
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert isinstance(body["run_id"], str)


def test_trigger_crawl_runs_pipeline_in_background():
    pipeline = StubPipeline()
    app = create_app(cron_secret="top-secret", pipeline=pipeline)
    response = asyncio.run(post(app, headers={"Authorization": "Bearer top-secret"}))

    assert len(pipeline.calls) == 1
    run_id = response.json()["run_id"]
    assert pipeline.calls[0] == run_id
    assert len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id)


def test_trigger_crawl_returns_202_when_pipeline_degrades():
    app = create_app(cron_secret="top-secret", pipeline=DegradedPipeline())
    response = asyncio.run(post(app, headers={"Authorization": "Bearer top-secret"}))

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert isinstance(body["run_id"], str)


def test_trigger_crawl_returns_202_when_pipeline_raises_http_exception():
    app = create_app(cron_secret="top-secret", pipeline=HttpExceptionPipeline())
    response = asyncio.run(post(app, headers={"Authorization": "Bearer top-secret"}))

    assert response.status_code == 202


def test_trigger_crawl_returns_202_for_unexpected_pipeline_error():
    app = create_app(cron_secret="top-secret", pipeline=ErrorPipeline())
    response = asyncio.run(post(app, headers={"Authorization": "Bearer top-secret"}))

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert isinstance(body["run_id"], str)


def test_telegram_webhook_rejects_invalid_secret():
    app = create_app(
        cron_secret="top-secret",
        pipeline=StubPipeline(),
        repository=StubRepository(),
        telegram_bot=StubTelegramBot(),
        telegram_webhook_secret="hook-secret",
    )

    response = asyncio.run(
        post(
            app,
            path="/api/v1/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "bad"},
            json={"message": {"text": "/start", "chat": {"id": 42, "type": "private"}, "from": {}}},
        )
    )

    assert response.status_code == 401


def test_telegram_webhook_subscribes_private_user():
    repository = StubRepository()
    telegram_bot = StubTelegramBot()
    app = create_app(
        cron_secret="top-secret",
        pipeline=StubPipeline(),
        repository=repository,
        telegram_bot=telegram_bot,
        telegram_webhook_secret="hook-secret",
    )

    response = asyncio.run(
        post(
            app,
            path="/api/v1/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
            json={
                "message": {
                    "text": "/start",
                    "chat": {"id": 42, "type": "private"},
                    "from": {"username": "viet", "first_name": "Viet"},
                }
            },
        )
    )

    assert response.status_code == 200
    assert repository.upsert_calls == [("42", "viet", "Viet")]
    assert telegram_bot.replies == [("42", "welcome")]


def test_telegram_webhook_returns_guidance_for_group_chat():
    repository = StubRepository()
    telegram_bot = StubTelegramBot()
    app = create_app(
        cron_secret="top-secret",
        pipeline=StubPipeline(),
        repository=repository,
        telegram_bot=telegram_bot,
        telegram_webhook_secret="hook-secret",
    )

    response = asyncio.run(
        post(
            app,
            path="/api/v1/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
            json={
                "message": {
                    "text": "/start",
                    "chat": {"id": -100, "type": "group"},
                    "from": {"username": "viet", "first_name": "Viet"},
                }
            },
        )
    )

    assert response.status_code == 200
    assert repository.upsert_calls == []
    assert telegram_bot.replies == [("-100", "private only")]


def test_telegram_webhook_status_reads_current_subscription_state():
    repository = StubRepository()
    repository.subscribers["42"] = {"chat_id": "42", "is_active": True}
    telegram_bot = StubTelegramBot()
    app = create_app(
        cron_secret="top-secret",
        pipeline=StubPipeline(),
        repository=repository,
        telegram_bot=telegram_bot,
        telegram_webhook_secret="hook-secret",
    )

    response = asyncio.run(
        post(
            app,
            path="/api/v1/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
            json={
                "message": {
                    "text": "/status",
                    "chat": {"id": 42, "type": "private"},
                    "from": {"username": "viet", "first_name": "Viet"},
                }
            },
        )
    )

    assert response.status_code == 200
    assert telegram_bot.replies == [("42", "active")]


def test_trigger_crawl_logs_failure_reason(caplog):
    caplog.set_level(logging.ERROR)
    app = create_app(cron_secret="top-secret", pipeline=ErrorPipeline())

    asyncio.run(post(app, headers={"Authorization": "Bearer top-secret"}))

    assert any(
        getattr(record, "event", None) == "trigger_crawl_failed"
        and getattr(record, "error_type", None) == "RuntimeError"
        and getattr(record, "error_message", None) == "boom"
        for record in caplog.records
    )


async def post(app, path="/api/v1/trigger-crawl", headers=None, json=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(path, headers=headers, json=json)
