"""Behavioral guards for complete, honest Georgian translation."""

import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from kartuli.bot import handle_message
from kartuli.translator import (
    DICTIONARY,
    TranslationError,
    is_complete_georgian_translation,
    translate_to_georgian,
    transliterate_georgian,
)


OWNER_PHRASE = "Привет, друг! Пойдём поужинаем?"
CORPUS_PATH = Path(__file__).parent / "fixtures" / "translation_corpus.json"


class TranslationSafetyTest(unittest.IsolatedAsyncioTestCase):
    async def test_dictionary_phrase_with_edge_punctuation_works_when_provider_is_down(self) -> None:
        with patch("deep_translator.GoogleTranslator") as translator:
            translator.return_value.translate.side_effect = RuntimeError("provider unavailable")
            self.assertEqual(await translate_to_georgian("Спасибо!"), "მადლობა")
            translator.assert_not_called()

    async def test_provider_failure_is_an_error_not_a_word_by_word_mixture(self) -> None:
        with patch("deep_translator.GoogleTranslator") as translator:
            translator.return_value.translate.side_effect = RuntimeError("provider unavailable")
            with self.assertRaises(TranslationError):
                await translate_to_georgian(OWNER_PHRASE)

    async def test_mixed_provider_result_is_rejected(self) -> None:
        with patch("deep_translator.GoogleTranslator") as translator:
            translator.return_value.translate.return_value = "გამარჯობა друг! пойдем поужинаем?"
            with self.assertRaises(TranslationError):
                await translate_to_georgian(OWNER_PHRASE)

    async def test_fully_georgian_provider_result_is_accepted(self) -> None:
        provider_result = "გამარჯობა, მეგობარო! წავიდეთ ვივახშმოთ?"
        with patch("deep_translator.GoogleTranslator") as translator:
            translator.return_value.translate.return_value = provider_result
            self.assertEqual(await translate_to_georgian(OWNER_PHRASE), provider_result)

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
