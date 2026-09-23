"""Behavioral checks for application and dependency logging."""

import io
import logging
import unittest

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


if __name__ == "__main__":
    unittest.main()
