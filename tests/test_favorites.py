"""Favorites persist by Telegram user and replay their saved audio."""

import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from kartuli.bot import favorites_callback, favorites_command, handle_message
from kartuli.favorites import CATEGORIES, FavoriteStore


class FavoriteStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db_path = Path(self.temporary.name) / "data" / "favorites.sqlite3"
        self.source_audio = Path(self.temporary.name) / "voice.mp3"
        self.source_audio.write_bytes(b"saved-mp3")

    def test_persists_per_user_without_duplicates_and_removes_one_card(self) -> None:
        store = FavoriteStore(self.db_path)
        first, created = store.add(11, "Спасибо", "მადლობა", "greetings", self.source_audio)
        self.assertTrue(created)
        self.assertEqual(first.audio_path.read_bytes(), b"saved-mp3")
        self.assertEqual(stat.S_IMODE(self.db_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(first.audio_path.stat().st_mode), 0o600)
        self.assertEqual(len(list(first.audio_path.parent.glob("*.mp3"))), 1)

        repeat, created = store.add(11, "Спасибо", "მადლობა", "other", self.source_audio)
        self.assertFalse(created)
        self.assertEqual(repeat.id, first.id)
        self.assertEqual(len(list(first.audio_path.parent.glob("*.mp3"))), 1)

        restarted = FavoriteStore(self.db_path)
        self.assertEqual(restarted.get(11, first.id), first)
        self.assertIsNone(restarted.get(22, first.id))
        self.assertEqual(restarted.counts(11), {"greetings": 1})
        self.assertEqual(restarted.counts(22), {})
        self.assertFalse(restarted.delete(22, first.id))
        self.assertTrue(restarted.delete(11, first.id))
        self.assertFalse(first.audio_path.exists())
        self.assertEqual(restarted.counts(11), {})

    def test_missing_database_restarts_as_empty_and_categories_are_closed(self) -> None:
        store = FavoriteStore(self.db_path)
        store.add(11, "Спасибо", "მადლობა", "greetings", self.source_audio)
        self.db_path.unlink()
        restarted = FavoriteStore(self.db_path)
        self.assertEqual(restarted.counts(11), {})
        self.assertEqual(list((self.db_path.parent / "audio").glob("*.mp3")), [])
        self.assertEqual(restarted.list_category(11, "greetings"), [])
        with self.assertRaises(ValueError):
            restarted.add(11, "Привет", "გამარჯობა", "custom", self.source_audio)
        self.assertEqual(len(CATEGORIES), 6)


class FavoriteBotTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db_path = Path(self.temporary.name) / "data" / "favorites.sqlite3"
        self.env_patch = patch.dict(os.environ, {"FAVORITES_DB_PATH": str(self.db_path)})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.source_audio = Path(self.temporary.name) / "provider.mp3"
        self.source_audio.write_bytes(b"one-generated-audio")
        self.context = MagicMock()
        self.context.bot.send_chat_action = AsyncMock()
        self.context.user_data = {}
        self.query = MagicMock()
        self.query.from_user.id = 11
        self.query.answer = AsyncMock()
        self.query.edit_message_text = AsyncMock()
        self.query.message.reply_text = AsyncMock()
        self.query.message.reply_voice = AsyncMock()
        self.update = MagicMock()
        self.update.callback_query = self.query

    async def test_add_then_play_uses_saved_file_and_card_id_buttons(self) -> None:
        translation = MagicMock()
        translation.message.text = "Спасибо"
        translation.message.reply_text = AsyncMock()
        with patch("kartuli.bot.translate_to_georgian", AsyncMock(return_value="მადლობა")):
            await handle_message(translation, self.context)
        translation_markup = translation.message.reply_text.await_args.kwargs["reply_markup"]
        add_data = translation_markup.inline_keyboard[0][1].callback_data
        self.assertTrue(add_data.startswith("fav:add:"))
        self.assertEqual(translation_markup.inline_keyboard[1][0].callback_data, "fav:show")
        self.assertLessEqual(len(add_data.encode()), 64)

        self.query.data = add_data
        await favorites_callback(self.update, self.context)
        category_markup = self.query.message.reply_text.await_args.kwargs["reply_markup"]
        self.assertEqual(len(category_markup.inline_keyboard), 6)
        self.query.data = category_markup.inline_keyboard[0][0].callback_data
        self.assertTrue(self.query.data.endswith(":greetings"))

        synthesize = AsyncMock(return_value=str(self.source_audio))
        with patch("kartuli.bot.generate_audio", synthesize):
            await favorites_callback(self.update, self.context)
            card = FavoriteStore().find(11, "მადლობა")
            self.assertIsNotNone(card)
            self.assertEqual(card.audio_path.read_bytes(), b"one-generated-audio")
            self.assertFalse(self.source_audio.exists())

            # A second category click must not create a duplicate or call TTS again.
            await favorites_callback(self.update, self.context)
            self.assertEqual(synthesize.await_count, 1)
            self.assertEqual(FavoriteStore().counts(11), {"greetings": 1})

            self.query.data = "fav:open:greetings:0"
            await favorites_callback(self.update, self.context)
            menu_markup = self.query.edit_message_text.await_args.kwargs["reply_markup"]
            self.query.data = menu_markup.inline_keyboard[0][0].callback_data
            self.assertEqual(self.query.data, f"fav:card:{card.id}:0")
            await favorites_callback(self.update, self.context)
            card_markup = self.query.edit_message_text.await_args.kwargs["reply_markup"]
            self.assertEqual(card_markup.inline_keyboard[0][0].callback_data, f"fav:play:{card.id}")
            self.assertEqual(card_markup.inline_keyboard[2][0].callback_data, f"fav:del:{card.id}")
            self.assertEqual(card_markup.inline_keyboard[1][0].callback_data, "fav:open:greetings:0")

            played = []

            async def capture_voice(audio_file):
                played.append(audio_file.read())

            self.query.message.reply_voice.side_effect = capture_voice
            self.query.data = f"fav:play:{card.id}"
            await favorites_callback(self.update, self.context)
            self.assertEqual(played, [b"one-generated-audio"])
            self.assertEqual(synthesize.await_count, 1)

            # Knowing another user's card id must not expose that user's audio.
            self.query.from_user.id = 22
            await favorites_callback(self.update, self.context)
            self.assertEqual(played, [b"one-generated-audio"])
            self.assertIn("недоступна", self.query.answer.await_args.args[0])
            self.query.from_user.id = 11

            self.query.data = f"fav:del:{card.id}"
            await favorites_callback(self.update, self.context)
            self.assertIsNone(FavoriteStore().get(11, card.id))
            self.assertFalse(card.audio_path.exists())

    async def test_missing_audio_and_missing_database_are_explicit(self) -> None:
        card, _ = FavoriteStore().add(11, "Спасибо", "მადლობა", "greetings", self.source_audio)
        card.audio_path.unlink()
        self.query.data = f"fav:play:{card.id}"
        await favorites_callback(self.update, self.context)
        self.assertIn("Аудиофайл пропал", self.query.answer.await_args.args[0])
        self.query.message.reply_voice.assert_not_awaited()

        self.db_path.unlink()
        command_update = MagicMock()
        command_update.effective_user.id = 11
        command_update.message.reply_text = AsyncMock()
        await favorites_command(command_update, self.context)
        self.assertIn("Избранное пусто", command_update.message.reply_text.await_args.args[0])

    async def test_empty_generated_audio_has_plain_error(self) -> None:
        self.context.user_data = {
            "audio_texts": {"saved": "მადლობა"},
            "favorite_sources": {"saved": "Спасибо"},
        }
        self.source_audio.write_bytes(b"")
        self.query.data = "fav:cat:saved:greetings"
        with patch("kartuli.bot.generate_audio", AsyncMock(return_value=str(self.source_audio))):
            await favorites_callback(self.update, self.context)
        self.assertIn("Не удалось озвучить", self.query.edit_message_text.await_args.args[0])
        self.assertEqual(FavoriteStore().counts(11), {})

    async def test_audio_provider_error_has_plain_error(self) -> None:
        self.context.user_data = {
            "audio_texts": {"saved": "მადლობა"},
            "favorite_sources": {"saved": "Спасибо"},
        }
        self.query.data = "fav:cat:saved:greetings"
        with patch("kartuli.bot.generate_audio", AsyncMock(side_effect=ValueError("internal detail"))):
            await favorites_callback(self.update, self.context)
        self.assertIn("Не удалось озвучить", self.query.edit_message_text.await_args.args[0])
        self.assertNotIn("internal detail", self.query.edit_message_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
