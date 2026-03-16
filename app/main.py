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


def create_app(cron_secret: str | None = None, pipeline=None) -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    active_pipeline = pipeline or NewsPipeline(
        crawler=build_default_crawler(settings),
        repository=SupabaseNewsRepository(
            url=settings.supabase_url,
            key=settings.supabase_key,
        ),
        summarizer=build_summarizer(settings),
        telegram=TelegramBot(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        ),
    )
    app.include_router(build_router(cron_secret or settings.cron_secret_key, active_pipeline))

    @app.get("/health")
    def healthcheck():
        return {"status": "ok"}

    return app


app = create_app()
