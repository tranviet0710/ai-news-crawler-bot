from __future__ import annotations

from app.services.llm_prompt import PROMPT, build_news_prompt
from app.services.schemas import NewsItem, SummarizedNews


class OpenAISummarizer:
    provider = "openai"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def summarize(self, item: NewsItem) -> SummarizedNews | None:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        if not self.model:
            raise RuntimeError("OPENAI_MODEL is not configured")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is not installed") from exc

        client = OpenAI(api_key=self.api_key)
        response = client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": PROMPT},
                {
                    "role": "user",
                    "content": build_news_prompt(item.title, item.source, item.summary, item.url),
                },
            ],
        )
        text = (response.output_text or "").strip()
        if not text or text.upper() == "SKIP":
            return None

        return SummarizedNews(summary=text, rationale="Accepted by OpenAI filter")
