"""Redact Telegram credentials before a configured handler formats a record."""

import logging
import re


REDACTED = "<TELEGRAM_TOKEN_REDACTED>"
# Also catch retired credentials absent from configuration. Deliberately accept
# variable ID/tail lengths (at least 20 tail characters), not only today's format.
TOKEN_PATTERN = re.compile(r"(?:bot)?[0-9]+:[A-Za-z0-9_-]{20,}")


class TelegramTokenFilter(logging.Filter):
    def __init__(self, token: str) -> None:
        super().__init__()
        self.token = token

    def redact(self, text: str) -> str:
        text = TOKEN_PATTERN.sub(REDACTED, text)
        if self.token:
            text = text.replace(self.token, REDACTED)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        # Render positional/dict arguments, including non-string objects, before
        # redaction so no deferred interpolation can reintroduce a credential.
        try:
            message = record.getMessage()
        except Exception:
            # A malformed logging call must not interrupt the bot handler or
            # fall back to logging's diagnostic dump of unsanitized arguments.
            message = f"{record.msg!s} [logging arguments: {record.args!r}]"
        record.msg = self.redact(message)
        record.args = ()
        if record.exc_info:
            record.exc_text = self.redact(
                logging.Formatter().formatException(record.exc_info)
            )
            # Keep the safe traceback, but prevent another handler from rendering
            # the original exception (and its chained causes) again.
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        if record.stack_info:
            record.stack_info = self.redact(record.stack_info)
        return True
