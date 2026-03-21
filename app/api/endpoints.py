import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

from app.core.logging import get_logger, log_event, sanitize_message


def build_router(cron_secret: str, pipeline, telegram_bot=None, repository=None, telegram_webhook_secret: str = "") -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["crawler"])
    logger = get_logger("api")

    def _run_pipeline_background(run_id: str) -> None:
        try:
            result = pipeline.run(run_id=run_id)
        except Exception as exc:
            secrets = pipeline._secrets() if hasattr(pipeline, "_secrets") else []
            log_event(
                logger,
                logging.ERROR,
                "trigger_crawl_failed",
                run_id=run_id,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error_type=type(exc).__name__,
                error_message=sanitize_message(str(exc), secrets=secrets),
            )
            return

        log_event(logger, logging.INFO, "trigger_crawl_finished", run_id=run_id, status_code=status.HTTP_200_OK)

    @router.post("/trigger-crawl", status_code=status.HTTP_202_ACCEPTED)
    def trigger_crawl(
        background_tasks: BackgroundTasks,
        authorization: str | None = Header(default=None),
    ):
        run_id = uuid4().hex
        log_event(logger, logging.INFO, "trigger_crawl_started", run_id=run_id)
        if not cron_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CRON_SECRET_KEY is not configured",
            )

        expected = f"Bearer {cron_secret}"
        if authorization != expected:
            log_event(
                logger,
                logging.WARNING,
                "trigger_crawl_unauthorized",
                run_id=run_id,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing bearer token",
            )

        log_event(logger, logging.INFO, "trigger_crawl_accepted", run_id=run_id, status_code=status.HTTP_202_ACCEPTED)
        background_tasks.add_task(_run_pipeline_background, run_id)
        return {"status": "accepted", "run_id": run_id}

    @router.post("/telegram/webhook")
    def telegram_webhook(
        update: dict,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ):
        if not telegram_webhook_secret:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="TELEGRAM_WEBHOOK_SECRET is not configured")
        if x_telegram_bot_api_secret_token != telegram_webhook_secret:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram webhook secret")
        if telegram_bot is None or repository is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram webhook dependencies are not configured")

        payload = telegram_bot.parse_command(update)
        if payload is None:
            return {"status": "ok"}

        if payload.command == "unsupported_chat":
            telegram_bot.send_text(payload.chat_id, telegram_bot.build_private_chat_only_message())
            return {"status": "ok"}

        if payload.command == "start":
            repository.upsert_subscriber(payload.chat_id, payload.username, payload.first_name)
            telegram_bot.send_text(payload.chat_id, telegram_bot.build_welcome_message())
        elif payload.command == "stop":
            repository.deactivate_subscriber(payload.chat_id)
            telegram_bot.send_text(payload.chat_id, "Da dung gui AI news.")
        elif payload.command == "status":
            subscriber = repository.get_subscriber(payload.chat_id)
            telegram_bot.send_text(payload.chat_id, telegram_bot.build_status_message(bool(subscriber and subscriber.get("is_active"))))
        elif payload.command == "help":
            telegram_bot.send_text(payload.chat_id, telegram_bot.build_help_message())

        return {"status": "ok"}

    return router
