"""Kartuli-Voice MVP — Telegram bot."""
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from kartuli.config import TELEGRAM_BOT_TOKEN
from kartuli.translator import translate_to_georgian, transliterate_georgian, transliterate_syllables, transliterate_english_syllables
from kartuli.tts import generate_audio

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start."""
    await update.message.reply_text(
        "🇬🇪 გამარჯობა! Я помогу тебе с грузинским языком.\n\n"
        "Просто напиши фразу на русском — я переведу, дам транскрипцию и озвучу.\n\n"
        "Пример: Спасибо, Помогите, Где ресторан?"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help."""
    await update.message.reply_text(
        "📖 Как использовать бота:\n\n"
        "1. Напиши фразу на русском\n"
        "2. Получи перевод на грузинский\n"
        "3. Получи транслитерацию (как произносить)\n"
        "4. Нажми ▶️ чтобы услышать произношение"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстовых сообщений."""
    text = update.message.text
    logger.info(f"Received: {text}")

    try:
        # Перевод на грузинский
        georgian_text = await translate_to_georgian(text)
        
        # Транслитерация
        translit_ru = transliterate_georgian(georgian_text)
        translit_ru_syll = transliterate_syllables(georgian_text)
        translit_en_syll = transliterate_english_syllables(georgian_text)

        # Ответ с кнопкой озвучки
        keyboard = [[InlineKeyboardButton("▶️ Озвучить", callback_data="speak")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🇬🇪 {georgian_text}\n\n"
            f"🗣 {translit_ru}\n"
            f"📝 {translit_ru_syll}\n"
            f"🔤 {translit_en_syll}",
            reply_markup=reply_markup,
        )

        # Сохраняем текст для озвучки
        context.user_data["last_text"] = georgian_text
    except Exception as e:
        logger.error(f"Message handler error: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка. Попробуйте ещё раз.")


async def speak_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка озвучки."""
    query = update.callback_query
    await query.answer()

    text = context.user_data.get("last_text")
    if not text:
        await query.edit_message_text("Нет текста для озвучки")
        return

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
        logger.error(f"Speak error: {e}", exc_info=True)
        try:
            await query.edit_message_text(f"Ошибка озвучки: {e}")
        except Exception:
            pass
    finally:
        # Удаляем временный файл
        if audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
            except Exception:
                pass


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
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()