import logging
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger, log_event, sanitize_message


def build_router(cron_secret: str, pipeline) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["crawler"])
    logger = get_logger("api")

    @router.post("/trigger-crawl")
    def trigger_crawl(authorization: str | None = Header(default=None)):
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

        log_event(logger, logging.INFO, "trigger_crawl_authorized", run_id=run_id, status_code=status.HTTP_200_OK)
        try:
            result = pipeline.run(run_id=run_id)
        except HTTPException:
            raise
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
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "status": "error",
                    "run_id": run_id,
                    "detail": "Unexpected crawl failure",
                },
            )

        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        log_event(logger, logging.INFO, "trigger_crawl_finished", run_id=run_id, status_code=status.HTTP_200_OK)
        return {"status": "ok", "run_id": run_id, "result": payload}

    return router
