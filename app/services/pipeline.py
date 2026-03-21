from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from app.core.logging import get_logger, sanitize_message


MAX_ERROR_ENTRIES = 10


@dataclass
class PipelineErrorEntry:
    stage: str
    url: str
    source: str
    provider: str
    error_type: str
    message: str
    recoverable: bool


@dataclass
class PipelineResult:
    total_fetched: int = 0
    skipped_existing: int = 0
    skipped_irrelevant: int = 0
    sent: int = 0
    failed_delivery: int = 0
    failed_processing: int = 0
    suppressed_error_count: int = 0
    errors: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def append_error(self, entry: PipelineErrorEntry) -> None:
        if len(self.errors) < MAX_ERROR_ENTRIES:
            self.errors.append(asdict(entry))
        else:
            self.suppressed_error_count += 1


class NewsPipeline:
    def __init__(self, crawler, repository, summarizer, telegram):
        self.crawler = crawler
        self.repository = repository
        self.summarizer = summarizer
        self.telegram = telegram
        self.logger = get_logger("pipeline")

    def run(self, *, run_id: str) -> PipelineResult:
        self._log(logging.INFO, "pipeline_started", run_id=run_id)
        items = self.crawler.fetch_recent_entries(run_id=run_id)
        result = PipelineResult(total_fetched=len(items))

        for item in items:
            self._log(logging.INFO, "item_check_exists_started", run_id=run_id, url=item.url, source=item.source, title=item.title)
            try:
                exists = self.repository.exists(item.url)
            except Exception as exc:
                self._record_error(result, "supabase_exists", item, exc)
                self._log_failure(logging.WARNING, "supabase_exists_failed", run_id, item, exc)
                result.failed_processing += 1
                continue

            if exists:
                result.skipped_existing += 1
                self._log(logging.INFO, "item_skipped_existing", run_id=run_id, url=item.url, source=item.source, title=item.title)
                continue

            try:
                self._log(logging.INFO, "llm_summarize_started", run_id=run_id, url=item.url, source=item.source, title=item.title, provider=self.summarizer.provider)
                ai_summary = self.summarizer.summarize(item)
                self._log(logging.INFO, "llm_summarize_succeeded", run_id=run_id, url=item.url, source=item.source, title=item.title, provider=self.summarizer.provider)
            except Exception as exc:
                self._record_error(result, "llm_summarize", item, exc)
                self._log_failure(logging.WARNING, "llm_summarize_failed", run_id, item, exc, provider=self.summarizer.provider)
                result.failed_processing += 1
                continue

            if ai_summary is None:
                result.skipped_irrelevant += 1
                self._log(logging.INFO, "item_skipped_irrelevant", run_id=run_id, url=item.url, source=item.source, title=item.title)
                continue

            try:
                self._log(logging.INFO, "supabase_save_started", run_id=run_id, url=item.url, source=item.source, title=item.title)
                self.repository.save(item, ai_summary)
                self._log(logging.INFO, "supabase_save_succeeded", run_id=run_id, url=item.url, source=item.source, title=item.title)
            except Exception as exc:
                self._record_error(result, "supabase_save", item, exc)
                self._log_failure(logging.WARNING, "supabase_save_failed", run_id, item, exc)
                result.failed_processing += 1
                continue

            subscribers = self._delivery_targets()
            for chat_id, is_subscriber in subscribers:
                if hasattr(self.repository, "create_delivery_attempt"):
                    try:
                        should_send = self.repository.create_delivery_attempt(item.url, chat_id)
                    except Exception as exc:
                        self._record_error(result, "telegram_delivery_prepare", item, exc)
                        self._log_failure(logging.WARNING, "telegram_delivery_prepare_failed", run_id, item, exc)
                        result.failed_delivery += 1
                        continue
                    if not should_send:
                        continue

                try:
                    self._log(logging.INFO, "telegram_send_started", run_id=run_id, url=item.url, source=item.source, title=item.title, chat_id=chat_id)
                    if hasattr(self.telegram, "send_news"):
                        self.telegram.send_news(chat_id, item, ai_summary)
                    else:
                        self.telegram.send(item, ai_summary)
                    if hasattr(self.repository, "mark_delivery_sent"):
                        self.repository.mark_delivery_sent(item.url, chat_id)
                    self._log(logging.INFO, "telegram_send_succeeded", run_id=run_id, url=item.url, source=item.source, title=item.title, chat_id=chat_id)
                    result.sent += 1
                except Exception as exc:
                    message = sanitize_message(str(exc), secrets=self._secrets())
                    if hasattr(self.repository, "mark_delivery_failed"):
                        self.repository.mark_delivery_failed(item.url, chat_id, message)
                    delivery_error = getattr(self.telegram, "classify_delivery_error", lambda error: None)(exc)
                    if (
                        is_subscriber
                        and delivery_error is not None
                        and getattr(delivery_error, "is_permanent", False)
                        and hasattr(self.repository, "deactivate_subscriber_for_delivery_error")
                    ):
                        self.repository.deactivate_subscriber_for_delivery_error(chat_id, getattr(delivery_error, "message", message))
                    self._record_error(result, "telegram_send", item, exc)
                    self._log_failure(logging.WARNING, "telegram_send_failed", run_id, item, exc, chat_id=chat_id)
                    result.failed_delivery += 1

        self._log(
            logging.INFO,
            "pipeline_completed",
            run_id=run_id,
            total_fetched=result.total_fetched,
            skipped_existing=result.skipped_existing,
            skipped_irrelevant=result.skipped_irrelevant,
            sent=result.sent,
            failed_delivery=result.failed_delivery,
            failed_processing=result.failed_processing,
            suppressed_error_count=result.suppressed_error_count,
        )
        return result

    def _record_error(self, result: PipelineResult, stage: str, item, exc: Exception) -> None:
        result.append_error(
            PipelineErrorEntry(
                stage=stage,
                url=item.url,
                source=item.source,
                provider=self.summarizer.provider,
                error_type=type(exc).__name__,
                message=sanitize_message(str(exc), secrets=self._secrets()),
                recoverable=True,
            )
        )

    def _log_failure(self, level: int, event: str, run_id: str, item, exc: Exception, **fields) -> None:
        self._log(
            level,
            event,
            run_id=run_id,
            url=item.url,
            source=item.source,
            title=item.title,
            stage=event.rsplit("_failed", 1)[0],
            error_type=type(exc).__name__,
            error_message=sanitize_message(str(exc), secrets=self._secrets()),
            **fields,
        )

    def _log(self, level: int, event: str, **fields) -> None:
        self.logger.log(level, event, extra={"event": event, **fields})

    def _secrets(self) -> list[str]:
        return [
            getattr(self.summarizer, "api_key", ""),
            getattr(self.repository, "key", ""),
            getattr(self.telegram, "bot_token", ""),
            getattr(self.telegram, "chat_id", ""),
        ]

    def _delivery_targets(self) -> list[tuple[str, bool]]:
        if hasattr(self.repository, "list_active_subscribers"):
            subscribers = [
                (str(subscriber.get("chat_id", "")), True)
                for subscriber in self.repository.list_active_subscribers()
                if subscriber.get("chat_id")
            ]
            if subscribers:
                return subscribers
        fallback_chat_id = getattr(self.telegram, "chat_id", "")
        if fallback_chat_id:
            return [(str(fallback_chat_id), False)]
        return []
