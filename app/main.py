from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.endpoints import build_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.crawler import HackerNewsCrawler, MultiSourceCrawler, NewsCrawler, RSSCrawler
from app.services.llm_factory import build_summarizer
from app.services.pipeline import NewsPipeline
from app.services.supabase_client import SupabaseNewsRepository
from app.services.telegram_bot import TelegramBot


def build_default_crawler(settings):
    rss_sources = [url for url in settings.rss_source_list if "hacker-news.firebaseio.com" not in url]
    crawlers: list[NewsCrawler] = [
        RSSCrawler(sources=rss_sources, lookback_hours=settings.crawl_lookback_hours),
    ]
    if any("hacker-news.firebaseio.com" in url for url in settings.rss_source_list):
        crawlers.append(HackerNewsCrawler(lookback_hours=settings.crawl_lookback_hours))
    return MultiSourceCrawler(crawlers)


def create_app(
    cron_secret: str | None = None,
    pipeline=None,
    repository=None,
    telegram_bot=None,
    telegram_webhook_secret: str | None = None,
) -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    active_repository = repository or SupabaseNewsRepository(
        url=settings.supabase_url,
        key=settings.supabase_key,
    )
    active_telegram_bot = telegram_bot or TelegramBot(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    active_pipeline = pipeline or NewsPipeline(
        crawler=build_default_crawler(settings),
        repository=active_repository,
        summarizer=build_summarizer(settings),
        telegram=active_telegram_bot,
    )
    app.include_router(
        build_router(
            cron_secret or settings.cron_secret,
            active_pipeline,
            telegram_bot=active_telegram_bot,
            repository=active_repository,
            telegram_webhook_secret=telegram_webhook_secret if telegram_webhook_secret is not None else settings.telegram_webhook_secret,
        )
    )

    @app.get("/health")
    def healthcheck():
        return {"status": "ok"}

    return app


def bootstrap_app() -> FastAPI:
    try:
        return create_app()
    except RuntimeError as exc:
        startup_error = exc

        @asynccontextmanager
        async def failing_lifespan(_app: FastAPI):
            raise startup_error
            yield

        return FastAPI(title="AI News Crawler", lifespan=failing_lifespan)


app = bootstrap_app()
