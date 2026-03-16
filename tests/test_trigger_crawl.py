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


async def post(app, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/api/v1/trigger-crawl", headers=headers)
