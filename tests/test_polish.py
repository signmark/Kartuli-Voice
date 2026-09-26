"""Visible progress and secret-safe failures in user flows."""

import asyncio
import io
import logging
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ChatAction

from kartuli.bot import handle_message, help_command, speak_callback, start
from kartuli.tts import _generate_edge_tts, generate_audio


class PolishTest(IsolatedAsyncioTestCase):
    async def test_initial_chat_action_failure_does_not_skip_translation(self):
        update = MagicMock()
        update.message.text = "Спасибо"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        context.bot.send_chat_action = AsyncMock(side_effect=RuntimeError("private detail"))
        translate = AsyncMock(return_value="მადლობა")
        with patch("kartuli.bot.translate_to_georgian", translate):
            await handle_message(update, context)
        translate.assert_awaited_once_with("Спасибо")
        self.assertIn("მადლობა", update.message.reply_text.await_args.args[0])

    async def test_chat_action_refresh_failure_does_not_lose_translation(self):
        update = MagicMock()
        update.message.text = "Спасибо"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        refreshed = asyncio.Event()

        async def chat_action(**_kwargs):
            if context.bot.send_chat_action.await_count == 2:
                refreshed.set()
                raise RuntimeError("private detail")

        context.bot.send_chat_action = AsyncMock(side_effect=chat_action)
        real_sleep = asyncio.sleep

        async def fast_sleep(_seconds):
            await real_sleep(0)

        async def translate(_text):
            await asyncio.wait_for(refreshed.wait(), timeout=1)
            return "მადლობა"

        with patch("kartuli.bot.asyncio.sleep", fast_sleep), patch("kartuli.bot.translate_to_georgian", translate):
            await handle_message(update, context)
        self.assertEqual(context.bot.send_chat_action.await_count, 2)
        self.assertIn("მადლობა", update.message.reply_text.await_args.args[0])

    async def test_start_and_help_open_favorites_by_button(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        for handler in (start, help_command):
            await handler(update, MagicMock())
            markup = update.message.reply_text.await_args.kwargs["reply_markup"]
            self.assertEqual(markup.inline_keyboard[0][0].callback_data, "fav:show")

    async def test_progress_precedes_translation_and_audio(self):
        context = MagicMock()
        context.user_data = {"audio_texts": {"saved": "მადლობა"}}
        context.bot.send_chat_action = AsyncMock()
        update = MagicMock()
        update.message.text = "Спасибо"
        update.message.reply_text = AsyncMock()
        update.effective_chat.id = 42

        async def translate(_text):
            context.bot.send_chat_action.assert_awaited_with(chat_id=42, action=ChatAction.TYPING)
            return "მადლობა"

        with patch("kartuli.bot.translate_to_georgian", translate):
            await handle_message(update, context)
        self.assertIn("მადლობა", update.message.reply_text.await_args.args[0])

        query = MagicMock()
        query.data = "speak:saved"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.message.chat.id = 42
        query.message.reply_voice = AsyncMock()
        update.callback_query = query

        async def audio(_text):
            context.bot.send_chat_action.assert_awaited_with(chat_id=42, action=ChatAction.RECORD_VOICE)
            return None

        with patch("kartuli.bot.generate_audio", audio):
            await speak_callback(update, context)
        self.assertIn("Не удалось", query.edit_message_text.await_args.args[0])

    async def test_tts_exception_text_never_reaches_log(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("kartuli.tts")
        logger.addHandler(handler)
        try:
            with patch("kartuli.tts._generate_edge_tts", AsyncMock(side_effect=RuntimeError("secret-value"))):
                self.assertIsNone(await generate_audio("მადლობა"))
        finally:
            logger.removeHandler(handler)
        self.assertIn("RuntimeError", stream.getvalue())
        self.assertNotIn("secret-value", stream.getvalue())

    async def test_edge_tts_exception_text_never_reaches_log(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("kartuli.tts")
        logger.addHandler(handler)
        try:
            with patch("kartuli.tts.edge_tts.Communicate", side_effect=RuntimeError("secret-value")):
                self.assertIsNone(await _generate_edge_tts("მადლობა"))
        finally:
            logger.removeHandler(handler)
        self.assertIn("RuntimeError", stream.getvalue())
        self.assertNotIn("secret-value", stream.getvalue())
