"""Kartuli-Voice MVP — TTS движок."""
import os
import logging
import tempfile
from gtts import gTTS

from kartuli.config import TTS_PROVIDER

logger = logging.getLogger(__name__)


async def generate_audio(text: str) -> str | None:
    """Генерация аудио из текста."""
    try:
        if TTS_PROVIDER == "gtts":
            return await _generate_gtts(text)
        else:
            logger.warning(f"Unknown TTS provider: {TTS_PROVIDER}")
            return None
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None


async def _generate_gtts(text: str) -> str | None:
    """Генерация через Google TTS."""
    try:
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name
        
        # Генерируем аудио
        tts = gTTS(text=text, lang="ka")  # "ka" — код грузинского языка
        tts.save(temp_path)
        
        logger.info(f"Generated audio: {temp_path}")
        return temp_path
    except Exception as e:
        logger.error(f"gTTS error: {e}")
        return None