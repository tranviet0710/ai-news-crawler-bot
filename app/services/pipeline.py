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

            try:
                self._log(logging.INFO, "telegram_send_started", run_id=run_id, url=item.url, source=item.source, title=item.title)
                self.telegram.send(item, ai_summary)
                self._log(logging.INFO, "telegram_send_succeeded", run_id=run_id, url=item.url, source=item.source, title=item.title)
            except Exception as exc:
                self._record_error(result, "telegram_send", item, exc)
                self._log_failure(logging.WARNING, "telegram_send_failed", run_id, item, exc)
                if hasattr(self.repository, "delete"):
                    try:
                        self._log(logging.INFO, "rollback_delete_started", run_id=run_id, url=item.url, source=item.source, title=item.title)
                        self.repository.delete(item.url)
                        self._log(logging.INFO, "rollback_delete_succeeded", run_id=run_id, url=item.url, source=item.source, title=item.title)
                    except Exception as rollback_exc:
                        self._record_error(result, "rollback_delete", item, rollback_exc)
                        self._log_failure(logging.ERROR, "rollback_delete_failed", run_id, item, rollback_exc)
                result.failed_delivery += 1
                continue

            result.sent += 1

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
