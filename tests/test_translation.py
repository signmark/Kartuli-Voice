"""Behavioral guards for complete, honest Georgian translation."""

import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from kartuli.bot import handle_message
from kartuli.translator import (
    DICTIONARY,
    TranslationError,
    TranslationUnavailableError,
    is_complete_georgian_translation,
    translate_to_georgian,
    transliterate_georgian,
)


OWNER_PHRASE = "Привет, друг! Пойдём поужинаем?"
CORPUS_PATH = Path(__file__).parent / "fixtures" / "translation_corpus.json"


class TranslationSafetyTest(unittest.IsolatedAsyncioTestCase):
    def provider(self, result="გამარჯობა, მეგობარო! წავიდეთ ვივახშმოთ?", status=200):
        response = MagicMock()
        response.raise_for_status.side_effect = (
            httpx.HTTPStatusError("provider failed", request=MagicMock(), response=MagicMock())
            if status != 200 else None
        )
        response.json.return_value = {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": result}]}}]
        }
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=response)
        return client

    async def test_dictionary_phrase_with_edge_punctuation_works_when_provider_is_down(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("kartuli.translator.httpx.AsyncClient") as provider:
            self.assertEqual(await translate_to_georgian("Спасибо!"), "მადლობა")
            provider.assert_not_called()

    async def test_missing_key_fails_closed_without_network(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("kartuli.translator.httpx.AsyncClient") as provider:
            with self.assertRaises(TranslationUnavailableError):
                await translate_to_georgian(OWNER_PHRASE)
            provider.assert_not_called()

    async def test_provider_failure_is_an_error_not_a_word_by_word_mixture(self) -> None:
        client = self.provider(status=503)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sentinel"}), patch("kartuli.translator.httpx.AsyncClient", return_value=client):
            with self.assertRaises(TranslationUnavailableError):
                await translate_to_georgian(OWNER_PHRASE)

    async def test_mixed_provider_result_is_rejected(self) -> None:
        client = self.provider("გამარჯობა друг! пойдем поужинаем?")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sentinel"}), patch("kartuli.translator.httpx.AsyncClient", return_value=client):
            with self.assertRaises(TranslationError):
                await translate_to_georgian(OWNER_PHRASE)

    async def test_fully_georgian_provider_result_is_accepted(self) -> None:
        provider_result = "გამარჯობა, მეგობარო! წავიდეთ ვივახშმოთ?"
        client = self.provider(provider_result)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sentinel"}), patch("kartuli.translator.httpx.AsyncClient", return_value=client) as provider:
            self.assertEqual(await translate_to_georgian(OWNER_PHRASE), provider_result)
            provider.assert_called_once_with(timeout=15)
            _, kwargs = client.post.await_args
            self.assertEqual(kwargs["headers"], {"x-goog-api-key": "sentinel"})
            self.assertEqual(kwargs["json"]["generationConfig"], {"temperature": 0})
            self.assertEqual(kwargs["json"]["contents"][0]["parts"][0]["text"], OWNER_PHRASE)

    async def test_timeout_and_non_stop_response_fail_closed(self) -> None:
        client = self.provider()
        client.post.side_effect = TimeoutError()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sentinel"}), patch("kartuli.translator.httpx.AsyncClient", return_value=client):
            with self.assertRaises(TranslationUnavailableError):
                await translate_to_georgian(OWNER_PHRASE)

        client = self.provider()
        client.post.return_value.json.return_value["candidates"][0]["finishReason"] = "MAX_TOKENS"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sentinel"}), patch("kartuli.translator.httpx.AsyncClient", return_value=client):
            with self.assertRaises(TranslationError):
                await translate_to_georgian(OWNER_PHRASE)

    async def test_provider_error_does_not_log_key(self) -> None:
        client = self.provider()
        client.post.side_effect = RuntimeError("sentinel")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sentinel"}), patch("kartuli.translator.httpx.AsyncClient", return_value=client), patch("kartuli.translator.logger.warning") as warning:
            with self.assertRaises(TranslationUnavailableError):
                await translate_to_georgian(OWNER_PHRASE)
        rendered = " ".join(str(value) for call in warning.call_args_list for value in (call.args + tuple(call.kwargs.values())))
        self.assertNotIn("sentinel", rendered)

    async def test_bot_shows_unavailable_error_without_transcription_or_audio_button(self) -> None:
        update = MagicMock()
        update.message.text = OWNER_PHRASE
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        with patch("kartuli.bot.translate_to_georgian", AsyncMock(side_effect=TranslationUnavailableError())):
            await handle_message(update, context)

        update.message.reply_text.assert_awaited_once_with(
            "Сервис перевода сейчас недоступен. Попробуйте ещё раз позже."
        )
        self.assertNotIn("audio_texts", context.user_data)

    async def test_mixed_network_response_reaches_bot_only_as_translation_error(self) -> None:
        update = MagicMock()
        update.message.text = OWNER_PHRASE
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        client = self.provider("გამარჯობა друг! пойдем поужинаем?")

        with patch.dict(os.environ, {"GEMINI_API_KEY": "sentinel"}), patch("kartuli.translator.httpx.AsyncClient", return_value=client):
            await handle_message(update, context)

        update.message.reply_text.assert_awaited_once_with(
            "Не удалось перевести фразу целиком. Попробуйте ещё раз позже."
        )
        self.assertNotIn("audio_texts", context.user_data)

    async def test_bot_shows_translation_error_without_transcription_or_audio_button(self) -> None:
        update = MagicMock()
        update.message.text = OWNER_PHRASE
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        with patch("kartuli.bot.translate_to_georgian", AsyncMock(side_effect=TranslationError())):
            await handle_message(update, context)

        update.message.reply_text.assert_awaited_once_with(
            "Не удалось перевести фразу целиком. Попробуйте ещё раз позже."
        )
        self.assertNotIn("last_text", context.user_data)


class FixedTranslationCorpusTest(unittest.TestCase):
    def test_corpus_is_fixed_large_and_matches_the_runtime_dictionary(self) -> None:
        corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(corpus), 20)
        for source, expected in corpus.items():
            with self.subTest(source=source):
                self.assertEqual(DICTIONARY.get(source), expected)
                self.assertTrue(is_complete_georgian_translation(expected))
                self.assertFalse(any("\u10a0" <= char <= "\u10ff" for char in transliterate_georgian(expected)))

        for source, translated in DICTIONARY.items():
            with self.subTest(runtime_dictionary_source=source):
                self.assertTrue(is_complete_georgian_translation(translated))

    def test_validator_rejects_every_non_georgian_letter(self) -> None:
        self.assertTrue(is_complete_georgian_translation("გამარჯობა!"))
        self.assertFalse(is_complete_georgian_translation("გამარჯობა friend"))
        self.assertFalse(is_complete_georgian_translation("გამარჯობა друг"))
        self.assertFalse(is_complete_georgian_translation("123!?"))


if __name__ == "__main__":
    unittest.main()
