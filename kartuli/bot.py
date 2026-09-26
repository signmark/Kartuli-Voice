"""Kartuli-Voice MVP — Telegram bot."""
import logging
import os
from pathlib import Path
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from kartuli.config import TELEGRAM_BOT_TOKEN
from kartuli.favorites import CATEGORIES, CATEGORY_LABELS, FavoriteStore
from kartuli.log_redaction import TelegramTokenFilter
from kartuli.translator import TranslationError, TranslationUnavailableError, translate_to_georgian, transliterate_georgian, transliterate_syllables, transliterate_english_syllables
from kartuli.tts import generate_audio


THIRD_PARTY_LOGGERS = ("httpx", "httpcore", "telegram.request")
MAX_AUDIO_TEXTS_PER_USER = 20
FAVORITES_PAGE_SIZE = 10


def configure_logging() -> None:
    """Keep useful logs, suppress request URLs, and redact Telegram tokens."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # Root logger filters do not see propagated dependency records. Protect
    # every output handler instead, and replace our filter on reconfiguration.
    for handler in logging.getLogger().handlers:
        for installed_filter in tuple(handler.filters):
            if isinstance(installed_filter, TelegramTokenFilter):
                handler.removeFilter(installed_filter)
        handler.addFilter(TelegramTokenFilter(TELEGRAM_BOT_TOKEN))
    for logger_name in THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


configure_logging()
logger = logging.getLogger(__name__)


def _remember_audio_text(
    context: ContextTypes.DEFAULT_TYPE, text: str, source_text: str | None = None
) -> str:
    """Store translated text behind a short callback-safe identifier."""
    audio_texts = context.user_data.setdefault("audio_texts", {})
    audio_id = secrets.token_urlsafe(8)
    while audio_id in audio_texts:
        audio_id = secrets.token_urlsafe(8)
    audio_texts[audio_id] = text
    if source_text is not None:
        context.user_data.setdefault("favorite_sources", {})[audio_id] = source_text

    while len(audio_texts) > MAX_AUDIO_TEXTS_PER_USER:
        oldest_id = next(iter(audio_texts))
        del audio_texts[oldest_id]
        context.user_data.get("favorite_sources", {}).pop(oldest_id, None)

    return audio_id


def build_application(token: str) -> Application:
    """Build the Telegram application without starting network polling."""
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("favorites", favorites_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    app.add_handler(
        CallbackQueryHandler(
            speak_callback,
            pattern=r"^speak(?::[A-Za-z0-9_-]+)?$",
        )
    )
    app.add_handler(CallbackQueryHandler(favorites_callback, pattern=r"^fav:"))

    return app


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start."""
    await update.message.reply_text(
        "🇬🇪 გამარჯობა! Я помогу тебе с грузинским языком.\n\n"
        "Просто напиши фразу на русском — я переведу, дам транскрипцию и озвучу.\n\n"
        "Примеры: Спасибо! Помогите! Где?"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help."""
    await update.message.reply_text(
        "📖 Как использовать бота:\n\n"
        "1. Напиши фразу на русском\n"
        "2. Получи перевод на грузинский\n"
        "3. Получи транслитерацию (как произносить)\n"
        "4. Нажми ▶️ чтобы услышать произношение"
        "\n5. Нажми ⭐ чтобы сохранить фразу, затем /favorites чтобы открыть избранное"
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain unsupported commands instead of leaving the user waiting."""
    await update.message.reply_text("Не знаю такую команду. Напишите /help или отправьте фразу на русском.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстовых сообщений."""
    text = update.message.text
    logger.info("Received message")

    try:
        # Перевод на грузинский
        georgian_text = await translate_to_georgian(text)
        
        # Транслитерация
        translit_ru = transliterate_georgian(georgian_text)
        translit_ru_syll = transliterate_syllables(georgian_text)
        translit_en_syll = transliterate_english_syllables(georgian_text)

        # Ответ с кнопкой озвучки
        audio_id = _remember_audio_text(context, georgian_text, text)
        keyboard = [
            [
                InlineKeyboardButton("▶️ Озвучить", callback_data=f"speak:{audio_id}"),
                InlineKeyboardButton("⭐ В избранное", callback_data=f"fav:add:{audio_id}"),
            ],
            [InlineKeyboardButton("📂 Избранное", callback_data="fav:show")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🇬🇪 {georgian_text}\n\n"
            f"🗣 {translit_ru}\n"
            f"📝 {translit_ru_syll}\n"
            f"🔤 {translit_en_syll}",
            reply_markup=reply_markup,
        )
    except TranslationUnavailableError:
        await update.message.reply_text(
            "Сервис перевода сейчас недоступен. Попробуйте ещё раз позже."
        )
    except TranslationError:
        await update.message.reply_text(
            "Не удалось перевести фразу целиком. Попробуйте ещё раз позже."
        )
    except Exception as e:
        logger.error(f"Message handler error: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка. Попробуйте ещё раз.")


async def speak_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка озвучки."""
    query = update.callback_query
    callback_data = query.data or ""
    _, _, audio_id = callback_data.partition(":")
    text = context.user_data.get("audio_texts", {}).get(audio_id)
    if not text:
        await query.answer("Текст для озвучки больше недоступен", show_alert=True)
        return
    await query.answer()

    audio_path = None
    try:
        # Генерация аудио
        audio_path = await generate_audio(text)
        
        if audio_path:
            with open(audio_path, "rb") as audio_file:
                await query.message.reply_voice(audio_file)
        else:
            await query.edit_message_text("Не удалось сгенерировать аудио")
    except Exception as e:
        logger.error("Speak error: errorClass=%s", type(e).__name__)
        try:
            await query.edit_message_text("Не удалось озвучить фразу. Попробуйте ещё раз позже.")
        except Exception:
            pass
    finally:
        # Удаляем временный файл
        if audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
            except Exception:
                pass


def _favorites_menu(store: FavoriteStore, user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    counts = store.counts(user_id)
    if not counts:
        return "Избранное пусто. Переведите фразу и нажмите ⭐ В избранное.", None
    buttons = [
        [InlineKeyboardButton(f"{label} ({counts.get(code, 0)})", callback_data=f"fav:open:{code}:0")]
        for code, label in CATEGORIES
    ]
    return "Избранное — выберите категорию:", InlineKeyboardMarkup(buttons)


def _category_menu(
    store: FavoriteStore, user_id: int, category: str, page: int
) -> tuple[str, InlineKeyboardMarkup]:
    cards = store.list_category(user_id, category)
    start_index = page * FAVORITES_PAGE_SIZE
    visible = cards[start_index : start_index + FAVORITES_PAGE_SIZE]
    if not visible:
        title = f"В категории «{CATEGORY_LABELS[category]}» пока нет фраз."
    else:
        title = f"{CATEGORY_LABELS[category]} — выберите фразу:"
    buttons = [
        [
            InlineKeyboardButton(
                f"{start_index + index + 1}. {card.georgian_text[:35]}",
                callback_data=f"fav:card:{card.id}:{page}",
            )
        ]
        for index, card in enumerate(visible)
    ]
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("◀️", callback_data=f"fav:open:{category}:{page - 1}"))
    if start_index + FAVORITES_PAGE_SIZE < len(cards):
        navigation.append(InlineKeyboardButton("▶️", callback_data=f"fav:open:{category}:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    buttons.append([InlineKeyboardButton("↩ Категории", callback_data="fav:list")])
    return title, InlineKeyboardMarkup(buttons)


async def favorites_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show this Telegram user's saved categories, including an empty state."""
    try:
        text, markup = _favorites_menu(FavoriteStore(), update.effective_user.id)
        await update.message.reply_text(text, reply_markup=markup)
    except Exception as error:
        logger.error("Favorites list failed: errorClass=%s", type(error).__name__)
        await update.message.reply_text("Не удалось открыть избранное. Попробуйте ещё раз позже.")


async def favorites_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle category selection and user-scoped favorite cards."""
    query = update.callback_query
    parts = (query.data or "").split(":")
    user_id = query.from_user.id
    store = FavoriteStore()

    try:
        action = parts[1]
        if action == "show" or action == "list":
            text, markup = _favorites_menu(store, user_id)
            await query.answer()
            if action == "show":
                await query.message.reply_text(text, reply_markup=markup)
            else:
                await query.edit_message_text(text, reply_markup=markup)
            return

        if action == "add":
            audio_id = parts[2]
            if audio_id not in context.user_data.get("audio_texts", {}):
                await query.answer("Фраза больше недоступна. Переведите её ещё раз.", show_alert=True)
                return
            buttons = [
                [InlineKeyboardButton(label, callback_data=f"fav:cat:{audio_id}:{code}")]
                for code, label in CATEGORIES
            ]
            await query.answer()
            await query.message.reply_text("Выберите категорию для фразы:", reply_markup=InlineKeyboardMarkup(buttons))
            return

        if action == "cat":
            audio_id, category = parts[2], parts[3]
            if category not in CATEGORY_LABELS:
                raise ValueError("Unknown category")
            translation = context.user_data.get("audio_texts", {}).get(audio_id)
            source = context.user_data.get("favorite_sources", {}).get(audio_id)
            if not translation or source is None:
                await query.answer("Фраза больше недоступна. Переведите её ещё раз.", show_alert=True)
                return
            existing = store.find(user_id, translation)
            if existing:
                await query.answer("Эта фраза уже в избранном", show_alert=True)
                return
            await query.answer()
            audio_source = None
            try:
                audio_source = await generate_audio(translation)
                if not audio_source:
                    await query.edit_message_text("Не удалось озвучить фразу. Попробуйте добавить её позже.")
                    return
                card, created = store.add(user_id, source, translation, category, audio_source)
            finally:
                if audio_source:
                    Path(audio_source).unlink(missing_ok=True)
            message = "Фраза сохранена в избранном." if created else "Эта фраза уже в избранном."
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📂 Открыть избранное", callback_data="fav:list")]]
                ),
            )
            return

        if action == "open":
            category, page = parts[2], int(parts[3])
            if category not in CATEGORY_LABELS or page < 0:
                raise ValueError("Invalid category page")
            text, markup = _category_menu(store, user_id, category, page)
            await query.answer()
            await query.edit_message_text(text, reply_markup=markup)
            return

        if action == "card":
            card_id, page = int(parts[2]), int(parts[3])
            card = store.get(user_id, card_id)
            if not card:
                await query.answer("Карточка больше недоступна.", show_alert=True)
                return
            buttons = [
                [InlineKeyboardButton("▶️ Воспроизвести", callback_data=f"fav:play:{card.id}")],
                [InlineKeyboardButton("↩ К фразам", callback_data=f"fav:open:{card.category}:{page}")],
                [InlineKeyboardButton("🗑 Удалить карточку", callback_data=f"fav:del:{card.id}")],
            ]
            await query.answer()
            await query.edit_message_text(
                f"{card.source_text} → {card.georgian_text}", reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        if action == "play":
            card = store.get(user_id, int(parts[2]))
            if not card:
                await query.answer("Карточка больше недоступна.", show_alert=True)
            elif not card.audio_path.is_file() or card.audio_path.stat().st_size == 0:
                await query.answer("Аудиофайл пропал. Удалите карточку и добавьте фразу заново.", show_alert=True)
            else:
                await query.answer()
                with card.audio_path.open("rb") as audio_file:
                    await query.message.reply_voice(audio_file)
            return

        if action == "del":
            card = store.get(user_id, int(parts[2]))
            if not card:
                await query.answer("Карточка больше недоступна.", show_alert=True)
                return
            store.delete(user_id, card.id)
            await query.answer()
            await query.edit_message_text(
                "Карточка удалена.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("↩ К фразам", callback_data=f"fav:open:{card.category}:0")]]
                ),
            )
            return

        raise ValueError("Unknown favorite action")
    except (IndexError, ValueError):
        await query.answer("Некорректная кнопка избранного.", show_alert=True)
    except Exception as error:
        logger.error("Favorites action failed: errorClass=%s", type(error).__name__)
        await query.message.reply_text("Не удалось выполнить действие с избранным. Попробуйте ещё раз позже.")


def main() -> None:
    """Запуск бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return

    app = build_application(TELEGRAM_BOT_TOKEN)

    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
