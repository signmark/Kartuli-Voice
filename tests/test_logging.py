"""Behavioral checks for application and dependency logging."""

import io
import logging
import unittest
from unittest.mock import patch

from telegram import Bot
from telegram.error import InvalidToken
from telegram.request import BaseRequest

from kartuli.log_redaction import REDACTED

from kartuli.bot import configure_logging


class LoggingConfigurationTest(unittest.TestCase):
    def test_dependency_request_urls_are_suppressed_but_app_logs_remain(self) -> None:
        configure_logging()

        output = io.StringIO()
        handler = logging.StreamHandler(output)
        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        try:
            logging.getLogger("httpx").info(
                "HTTP Request: GET https://api.telegram.org/redacted/getUpdates"
            )
            logging.getLogger("kartuli.bot").info("Bot started")
        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(original_level)

        rendered = output.getvalue()
        self.assertNotIn("api.telegram.org", rendered)
        self.assertIn("Bot started", rendered)

    def test_all_request_loggers_are_warning_or_stricter(self) -> None:
        configure_logging()

        for logger_name in ("httpx", "httpcore", "telegram.request"):
            with self.subTest(logger_name=logger_name):
                self.assertGreaterEqual(
                    logging.getLogger(logger_name).getEffectiveLevel(),
                    logging.WARNING,
                )


# Synthetic values only; B represents a retired credential absent from config.
TOKEN_A = "123456789:" + "A" * 35
TOKEN_B = "987654321:" + "b_-" * 12


class RejectedTokenRequest(BaseRequest):
    @property
    def read_timeout(self):
        return None

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, **kwargs):
        return 401, b'{"ok":false,"error_code":401,"description":"Unauthorized"}'


class TokenRedactionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.outputs = [io.StringIO(), io.StringIO()]
        self.handlers = [logging.StreamHandler(output) for output in self.outputs]
        for handler in self.handlers:
            handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        self.root = logging.getLogger()
        self.handlers_patch = patch.object(self.root, "handlers", self.handlers)
        self.handlers_patch.start()
        self.addCleanup(self.handlers_patch.stop)
        self.token_patch = patch("kartuli.bot.TELEGRAM_BOT_TOKEN", TOKEN_A)
        self.token_patch.start()
        self.addCleanup(self.token_patch.stop)
        self.logger = logging.getLogger("telegram.ext.Application")
        self.logger_patch = patch.multiple(
            self.logger, level=logging.INFO, propagate=True, handlers=[], disabled=False
        )
        self.logger_patch.start()
        self.addCleanup(self.logger_patch.stop)
        configure_logging()

    def assert_safe(self, *retained):
        for output in self.outputs:
            rendered = output.getvalue()
            self.assertNotIn(TOKEN_A, rendered)
            self.assertNotIn(TOKEN_B, rendered)
            self.assertIn(REDACTED, rendered)
            for fragment in retained:
                self.assertIn(fragment, rendered)

    def test_child_logger_messages_and_argument_formats(self):
        self.logger.error("Literal token " + TOKEN_A)
        self.logger.error("Request https://api.telegram.org/bot%s/getMe", TOKEN_B)
        self.logger.error("Retired %(token)s context preserved", {"token": TOKEN_B})
        self.logger.error(InvalidToken(TOKEN_A))
        self.assert_safe("ERROR telegram.ext.Application", "Request", "/getMe", "context preserved")

    def test_malformed_arguments_do_not_escape_or_expose_tokens(self):
        self.logger.error("Missing argument %s %s", TOKEN_B)
        self.logger.error("Missing mapping %(missing)s", {"token": TOKEN_A})
        self.assert_safe("Missing argument", "Missing mapping", "logging arguments")

    async def test_real_invalid_token_traceback_from_telegram_is_safe(self):
        bot = Bot(TOKEN_B, request=RejectedTokenRequest(), get_updates_request=RejectedTokenRequest())
        try:
            await bot.initialize()
        except InvalidToken:
            self.logger.exception("Bot initialization failed")
        else:
            self.fail("Telegram initialization should reject the synthetic token")
        finally:
            await bot.shutdown()
        self.assert_safe(
            "ERROR telegram.ext.Application", "Bot initialization failed",
            "Traceback (most recent call last)", "InvalidToken", "Unauthorized",
            "was rejected by the server", "direct cause",
        )

    def test_cached_exception_and_stack_text_are_safe(self):
        record = self.logger.makeRecord(
            self.logger.name, logging.ERROR, __file__, 1, "Cached failure", (), None
        )
        record.exc_text = "InvalidToken: " + TOKEN_B
        record.stack_info = "Stack context " + TOKEN_A
        self.logger.handle(record)
        self.assert_safe("InvalidToken:", "Stack context", "Cached failure")

    def test_configured_value_is_redacted_even_without_token_shape(self):
        with patch("kartuli.bot.TELEGRAM_BOT_TOKEN", "synthetic-malformed-credential"):
            configure_logging()
        self.logger.error("Invalid setting %s", "synthetic-malformed-credential")
        for output in self.outputs:
            self.assertNotIn("synthetic-malformed-credential", output.getvalue())
        self.assert_safe("Invalid setting")

    def test_reconfiguration_preserves_safe_context(self):
        configure_logging()
        self.logger.error("Old %s new %s; retry 12:30", TOKEN_B, TOKEN_A)
        self.assert_safe("Old", "new", "retry 12:30")


if __name__ == "__main__":
    unittest.main()
