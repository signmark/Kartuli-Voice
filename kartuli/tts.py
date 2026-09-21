"""Kartuli-Voice MVP — TTS движок (Edge TTS)."""
import os
import logging
import tempfile
import asyncio
import edge_tts

from kartuli.config import TTS_PROVIDER

logger = logging.getLogger(__name__)

# Georgian voice for Edge TTS
VOICE = "ka-GE-EkaNeural"


async def generate_audio(text: str) -> str | None:
    """Генерация аудио из текста."""
    try:
        return await _generate_edge_tts(text)
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None


async def _generate_edge_tts(text: str) -> str | None:
    """Генерация через Edge TTS."""
    try:
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name
        
        # Генерируем аудио
        communicate = edge_tts.Communicate(text, VOICE)
        await communicate.save(temp_path)
        
        logger.info(f"Generated audio: {temp_path}")
        return temp_path
    except Exception as e:
        logger.error(f"Edge TTS error: {e}")
        return None