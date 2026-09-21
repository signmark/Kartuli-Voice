"""Kartuli-Voice MVP — Telegram bot."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from kartuli.config import TELEGRAM_BOT_TOKEN
from kartuli.translator import translate_to_georgian, transliterate_georgian
from kartuli.tts import generate_audio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start."""
    await update.message.reply_text(
        "🇬🇪 გამარჯობა! Я помогу тебе с грузинским языком.\n\n"
        "Просто напиши фразу на русском — я переведу, дам транскрипцию и озвучу.\n\n"
        "Пример: Как сказать «Спасибо» по-грузински?"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help."""
    await update.message.reply_text(
        "📖 Как использовать бота:\n\n"
        "1. Напиши фразу на русском\n"
        "2. Получи перевод на грузинский\n"
        "3. Получи транскрипцию (как произносить)\n"
        "4. Нажми ▶️ чтобы услышать произношение\n\n"
        "Команды:\n"
        "/start — начать\n"
        "/help — эта справка"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстовых сообщений."""
    text = update.message.text
    logger.info(f"Received: {text}")

    # Перевод на грузинский
    georgian_text = await translate_to_georgian(text)
    
    # Транслитерация
    transliteration = transliterate_georgian(georgian_text)

    # Ответ с кнопкой озвучки
    keyboard = [[InlineKeyboardButton("▶️ Озвучить", callback_data="speak")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🇬🇪 {georgian_text}\n\n"
        f"🗣 {transliteration}",
        reply_markup=reply_markup,
    )

    # Сохраняем текст для озвучки
    context.user_data["last_text"] = georgian_text


async def speak_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка озвучки."""
    query = update.callback_query
    await query.answer()

    text = context.user_data.get("last_text")
    if not text:
        await query.edit_message_text("Нет текста для озвучки")
        return

    # Генерация аудио
    audio_path = await generate_audio(text)
    
    if audio_path:
        await query.message.reply_voice(open(audio_path, "rb"))
    else:
        await query.edit_message_text("Ошибка генерации аудио")


def main() -> None:
    """Запуск бота."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(speak_callback, pattern="^speak$"))

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()