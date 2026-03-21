from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI News Crawler"
    llm_provider: str = Field(default="groq", alias="LLM_PROVIDER")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    telegram_webhook_secret: str = Field(default="", alias="TELEGRAM_WEBHOOK_SECRET")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_key: str = Field(default="", alias="SUPABASE_KEY")
    cron_secret: str = Field(default="", validation_alias=AliasChoices("CRON_SECRET", "CRON_SECRET_KEY"))
    groq_model: str = Field(default="llama-3.1-8b-instant", alias="GROQ_MODEL")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    crawl_lookback_hours: int = Field(default=2, alias="CRAWL_LOOKBACK_HOURS")
    rss_sources: str = Field(
        default=(
            "https://openai.com/blog/rss.xml,"
            "https://blog.google/technology/ai/rss/,"
            "https://raw.githubusercontent.com/Olshansk/rss-feeds/refs/heads/main/feeds/feed_anthropic_news.xml,"
            "https://techcrunch.com/category/artificial-intelligence/feed/,"
            "https://huggingface.co/blog/feed.xml,"
            "https://aws.amazon.com/blogs/machine-learning/feed/,"
            "https://research.google/blog/rss/,"
            "https://engineering.fb.com/feed/,"
            "https://venturebeat.com/category/ai/feed/,"
            "https://news.mit.edu/rss/topic/artificial-intelligence2,"
            "https://bair.berkeley.edu/blog/feed.xml,"
            "https://www.technologyreview.com/topic/artificial-intelligence/feed/,"
            "https://hacker-news.firebaseio.com/v0/topstories.json"
        ),
        alias="RSS_SOURCES",
    )

    @property
    def rss_source_list(self) -> list[str]:
        return [item.strip() for item in self.rss_sources.split(",") if item.strip()]

    @property
    def cron_secret_key(self) -> str:
        return self.cron_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()
