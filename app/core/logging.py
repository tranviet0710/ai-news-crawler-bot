from __future__ import annotations

import json
import logging
import re
import sys
from typing import Iterable


_LOGGER_NAME = "ai_news_crawler"
_CONFIGURED = False
_REDACT_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)([^\s]+)"),
    re.compile(r"(?i)(token=)([^\s&]+)"),
    re.compile(r"(?i)(api[_-]?key=)([^\s&]+)"),
    re.compile(r"(?i)([a-z0-9_]*key=)([^\s&]+)"),
    re.compile(r"(?i)(secret=)([^\s&]+)"),
    re.compile(r"(?i)(chat_id=)([^\s&]+)"),
]
_URL_USERINFO_PATTERN = re.compile(r"(https?://)([^/@\s]+@)")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            }:
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=True, default=str)


def mask_chat_id(value: str) -> str:
    if len(value) <= 4:
        return "[REDACTED]"
    return "*" * (len(value) - 4) + value[-4:]


def sanitize_message(message: str, secrets: Iterable[str] | None = None) -> str:
    sanitized = message
    sanitized = _URL_USERINFO_PATTERN.sub(r"\1[REDACTED]@", sanitized)
    for pattern in _REDACT_PATTERNS:
        if pattern.pattern.lower().startswith("(?i)(chat_id="):
            sanitized = pattern.sub(lambda m: m.group(1) + mask_chat_id(m.group(2)), sanitized)
        else:
            sanitized = pattern.sub(lambda m: m.group(1) + "[REDACTED]", sanitized)

    for secret in secrets or []:
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    return sanitized


def configure_logging() -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)
    if not _CONFIGURED:
        logger.setLevel(logging.INFO)
        logger.propagate = True
        logger.handlers = []
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        _CONFIGURED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def log_event(logger: logging.Logger, level: int, event: str, **fields) -> None:
    logger.log(level, event, extra={"event": event, **fields})
