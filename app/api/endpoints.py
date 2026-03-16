import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

from app.core.logging import get_logger, log_event, sanitize_message


def build_router(cron_secret: str, pipeline) -> APIRouter:
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

    return router
