"""Kartuli-Voice MVP — TTS движок (Edge TTS)."""
import logging
from pathlib import Path
import tempfile
import edge_tts

logger = logging.getLogger(__name__)

# Georgian voice for Edge TTS
VOICE = "ka-GE-EkaNeural"


async def generate_audio(text: str) -> str | None:
    """Генерация аудио из текста."""
    try:
        return await _generate_edge_tts(text)
    except Exception as e:
        logger.error("TTS error: errorClass=%s", type(e).__name__)
        return None


async def _generate_edge_tts(text: str) -> str | None:
    """Генерация через Edge TTS."""
    temp_path = None
    try:
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name
        
        # Генерируем аудио
        communicate = edge_tts.Communicate(text, VOICE)
        await communicate.save(temp_path)
        
        logger.info("Generated audio")
        return temp_path
    except Exception as e:
        logger.error("Edge TTS error: errorClass=%s", type(e).__name__)
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
        return None
