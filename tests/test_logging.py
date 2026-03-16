import logging


def test_mask_secret_redacts_known_values():
    from app.core.logging import sanitize_message

    text = "token=abc123 secret=xyz789"
    sanitized = sanitize_message(text, secrets=["abc123", "xyz789"])

    assert "abc123" not in sanitized
    assert "xyz789" not in sanitized
    assert sanitized.count("[REDACTED]") == 2


def test_sanitize_message_redacts_url_userinfo():
    from app.core.logging import sanitize_message

    sanitized = sanitize_message("https://user:pass@example.com/feed.xml")

    assert "user:pass" not in sanitized
    assert sanitized == "https://[REDACTED]@example.com/feed.xml"


def test_configure_logging_is_idempotent():
    from app.core.logging import configure_logging

    logger = configure_logging()
    configure_logging()

    handlers = [handler for handler in logger.handlers if isinstance(handler, logging.StreamHandler)]
    assert len(handlers) == 1
