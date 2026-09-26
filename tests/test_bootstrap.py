"""Behavioral acceptance for startup commands and recoverable failures."""

from datetime import datetime, timezone
import importlib
import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Chat, Message, MessageEntity, Update, User

from kartuli.bot import build_application, favorites_command, main, speak_callback, start, unknown_command
from kartuli import config


class BotBootstrapTest(unittest.IsolatedAsyncioTestCase):
    def test_telegram_token_follows_environment(self) -> None:
        try:
            with patch("dotenv.load_dotenv"):
                for value in ("synthetic-one", "synthetic-two"):
                    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": value}):
                        self.assertEqual(importlib.reload(config).TELEGRAM_BOT_TOKEN, value)
        finally:
            with patch("dotenv.load_dotenv"):
                importlib.reload(config)

    def test_main_starts_polling_with_configured_token(self) -> None:
        with patch("kartuli.bot.TELEGRAM_BOT_TOKEN", "synthetic-token"), patch("kartuli.bot.build_application") as builder:
            main()
        builder.assert_called_once_with("synthetic-token")
        builder.return_value.run_polling.assert_called_once_with(drop_pending_updates=True)

    @staticmethod
    def command_update(command: str, bot) -> Update:
        user = User(id=1, first_name="Test", is_bot=False)
        chat = Chat(id=1, type="private")
        message = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=chat,
            from_user=user,
            text=command,
            entities=(MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=len(command)),),
        )
        message.set_bot(bot)
        return Update(update_id=1, message=message)

    async def test_start_responds_promptly_without_external_calls(self) -> None:
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        started = time.perf_counter()
        await start(update, MagicMock())
        self.assertLess(time.perf_counter() - started, 2)
        update.message.reply_text.assert_awaited_once()
        self.assertIn("напиши", update.message.reply_text.await_args.args[0].lower())

    async def test_unknown_command_reaches_fallback_after_known_commands(self) -> None:
        app = build_application("123456:TEST_TOKEN")
        app.bot._bot_user = User(id=2, first_name="Test Bot", is_bot=True, username="test_bot")
        handlers = app.handlers[0]
        for command, expected in (("/start", start), ("/favorites", favorites_command), ("/whatnow", unknown_command)):
            with self.subTest(command=command):
                update = self.command_update(command, app.bot)
                first_match = next(handler for handler in handlers if handler.check_update(update))
                self.assertIs(first_match.callback, expected)

        update = MagicMock()
        update.message.reply_text = AsyncMock()
        await unknown_command(update, MagicMock())
        update.message.reply_text.assert_awaited_once()
        self.assertIn("/help", update.message.reply_text.await_args.args[0])

    async def test_tts_failure_is_plain_and_does_not_escape_callback(self) -> None:
        query = MagicMock()
        query.data = "speak:stored"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        context.user_data = {"audio_texts": {"stored": "მადლობა"}}

        with patch("kartuli.bot.generate_audio", AsyncMock(side_effect=RuntimeError("internal detail"))):
            await speak_callback(update, context)

        query.edit_message_text.assert_awaited_once_with(
            "Не удалось озвучить фразу. Попробуйте ещё раз позже."
        )


if __name__ == "__main__":
    unittest.main()
