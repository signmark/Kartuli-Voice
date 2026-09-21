# Kartuli-Voice MVP

AI-ассистент с озвучкой грузинского языка.

## Стек

- **Backend**: Python 3.11+ / FastAPI
- **Bot**: python-telegram-bot
- **TTS**: ElevenLabs API (премиум) / Google TTS (бесплатный)
- **Перевод**: OpenAI GPT-4o-mini
- **Хранение**: SQLite (MVP)

## Быстрый старт

```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка окружения
cp .env.example .env
# Заполнить переменные в .env

# Запуск
python -m kartuli.bot
```

## Структура проекта

```
kartuli-voice-mvp/
├── kartuli/
│   ├── __init__.py
│   ├── bot.py          # Telegram bot
│   ├── api.py          # FastAPI endpoints
│   ├── translator.py   # LLM перевод и транслитерация
│   ├── tts.py          # TTS движок
│   ├── storage.py      # Хранение избранных
│   └── config.py       # Конфигурация
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

## Задачи

1. ✅ Инфраструктура проекта
2. ⬜ Перевод и транслитерация
3. ⬜ TTS движок
4. ⬜ Избранное (Карточки)
5. ⬜ UX и полировка