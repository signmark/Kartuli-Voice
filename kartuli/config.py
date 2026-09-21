"""Kartuli-Voice MVP configuration."""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# OpenAI (для перевода)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# TTS
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "gtts")  # "gtts" или "elevenlabs"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///kartuli.db")