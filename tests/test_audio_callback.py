"""Behavioral guards for message-bound audio buttons."""

import unittest
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

from telegram import CallbackQuery, Update, User
from telegram.ext import CallbackQueryHandler

from kartuli.bot import (
    MAX_AUDIO_TEXTS_PER_USER,
    _remember_audio_text,
    build_application,
    handle_message,
    speak_callback,
)


TEXT_A = "მადლობა"
TEXT_B = "გამარჯობა"


class MessageBoundAudioTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _callback_update(callback_data: str) -> Update:
        query = CallbackQuery(
            id="callback-id",
            from_user=User(id=1, first_name="Test", is_bot=False),
            chat_instance="chat-instance",
            data=callback_data,
        )
        return Update(update_id=1, callback_query=query)

    def test_audio_text_storage_is_bounded(self) -> None:
        context = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        context.user_data = {}

        with patch("kartuli.bot.secrets.token_urlsafe", side_effect=[f"id-{i}" for i in range(21)]):
            for i in range(21):
                _remember_audio_text(context, f"text-{i}")

        stored = context.user_data["audio_texts"]
        self.assertEqual(len(stored), MAX_AUDIO_TEXTS_PER_USER)
        self.assertNotIn("id-0", stored)
        self.assertEqual(stored["id-20"], "text-20")

    async def test_each_button_speaks_its_own_message_after_a_later_translation(self) -> None:
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        context.user_data = {}

        with patch(
            "kartuli.bot.translate_to_georgian",
            AsyncMock(side_effect=[TEXT_A, TEXT_B]),
        ):
            update.message.text = "спасибо"
            await handle_message(update, context)
            update.message.text = "привет"
            await handle_message(update, context)

        callbacks = [
            call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
            for call in update.message.reply_text.await_args_list
        ]
        self.assertEqual(len(set(callbacks)), 2)
        for callback in callbacks:
            self.assertLessEqual(len(callback.encode("utf-8")), 64)
            self.assertNotIn(TEXT_A, callback)
            self.assertNotIn(TEXT_B, callback)

        generated = []

        async def fake_generate_audio(text: str) -> str:
            generated.append(text)
            return "/tmp/fake-audio.mp3"

        for callback in callbacks:
            query = MagicMock()
            query.data = callback
            query.answer = AsyncMock()
            query.message.reply_voice = AsyncMock()
            audio_update = MagicMock()
            audio_update.callback_query = query
            with (
                patch("kartuli.bot.generate_audio", fake_generate_audio),
                patch("builtins.open", mock_open(read_data=b"audio")),
                patch("kartuli.bot.os.path.exists", return_value=False),
            ):
                await speak_callback(audio_update, context)

        self.assertEqual(generated, [TEXT_A, TEXT_B])

    async def test_generated_and_legacy_buttons_reach_registered_callback_handler(self) -> None:
        update = MagicMock()
        update.message.text = "спасибо"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        context.user_data = {}

        with patch(
            "kartuli.bot.translate_to_georgian",
            AsyncMock(return_value=TEXT_A),
        ):
            await handle_message(update, context)

        callback_data = (
            update.message.reply_text.await_args.kwargs["reply_markup"]
            .inline_keyboard[0][0]
            .callback_data
        )
        app = build_application("123456:TEST_TOKEN")
        callback_handlers = [
            handler
            for handlers in app.handlers.values()
            for handler in handlers
            if isinstance(handler, CallbackQueryHandler)
            and handler.check_update(self._callback_update(callback_data))
        ]

        self.assertEqual(len(callback_handlers), 1)
        handler = callback_handlers[0]
        self.assertTrue(handler.check_update(self._callback_update(callback_data)))
        self.assertTrue(handler.check_update(self._callback_update("speak")))
        self.assertFalse(handler.check_update(self._callback_update("other")))

    async def test_unknown_audio_id_does_not_call_tts(self) -> None:
        query = MagicMock()
        query.data = "speak:missing"
        query.answer = AsyncMock()
        query.message.reply_voice = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        context.user_data = {"audio_texts": {}}

        with patch("kartuli.bot.generate_audio", AsyncMock()) as generate_audio:
            await speak_callback(update, context)

        query.answer.assert_awaited_once_with(
            "Текст для озвучки больше недоступен",
            show_alert=True,
        )
        generate_audio.assert_not_awaited()
        query.message.reply_voice.assert_not_awaited()

    async def test_full_source_text_is_not_logged(self) -> None:
        update = MagicMock()
        update.message.text = "личная фраза"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        context.user_data = {}

        with (
            patch("kartuli.bot.translate_to_georgian", AsyncMock(return_value=TEXT_A)),
            self.assertLogs("kartuli.bot", level="INFO") as captured,
        ):
            await handle_message(update, context)

        self.assertNotIn(update.message.text, "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
