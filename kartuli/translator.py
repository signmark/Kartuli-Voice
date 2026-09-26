"""Kartuli-Voice MVP — перевод и транслитерация."""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

SOURCE_EDGE_PUNCTUATION = " \t\r\n.,!?;:…—–-«»\"'()[]{}"
GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_TIMEOUT_SECONDS = 15


class TranslationError(RuntimeError):
    """The source phrase could not be translated completely and safely."""


class TranslationUnavailableError(TranslationError):
    """The translation provider is unavailable."""

# Базовый словарь для MVP (без API)
DICTIONARY = {
    "спасибо": "მადლობა",
    "привет": "გამარჯობა",
    "пожалуйста": "გთხოვთ",
    "да": "კი",
    "нет": "არა",
    "хорошо": "კარგი",
    "доброе утро": "დილა მშვიდობისა",
    "добрый день": "დღე მშვიდობისა",
    "добрый вечер": "საღამო მშვიდობისა",
    "до свидания": "ნახვამდის",
    "извините": "უკაცრავად",
    "помогите": "დამეხმარეთ",
    "где": "სად",
    "сколько": "რამდენი",
    "что": "რა",
    "как": "როგორ",
    "магазин": "მაღაზია",
    "ресторан": "რესტორანი",
    "такси": "ტაქსი",
    "гостиница": "სასტუმრო",
    "аэропорт": "აეროპორტი",
    "вода": "წყალი",
    "еда": "საჭმელი",
    "деньги": "ფული",
    "билет": "ბილეთი",
    "притормозите здесь": "აქ შეანელეთ",
    "притормозите здесь пожалуйста": "აქ შეანელეთ, თუ შეიძლება",
    "как вас зовут": "რა გქვიათ",
    "как тебя зовут": "რა გქვია",
    "меня зовут": "მე მქვია",
    "приятно познакомиться": "სასიამოვნოა თქვენი გაცნობა",
    "я не понимаю": "არ მესმის",
    "скажите пожалуйста": "მითხარით, თუ შეიძლება",
    "где находится": "სად არის",
    "сколько стоит": "რამდენი ღირს",
    "я хочу": "მინდა",
    "можно мне": "შემიძლია",
    "спасибо большое": "დიდი მადლობა",
    "не за что": "არაფრის",
    "будьте добры": "იყავით კეთილი",
    "счет пожалуйста": "ანგარიში, თუ შეიძლება",
    "кафе": "კაფე",
    "ресторан": "რესტორანი",
}

# Транслитерация грузинских букв → русская кириллица
TRANSLIT_RU = {
    "ა": "а", "ბ": "б", "გ": "г", "დ": "д", "ე": "е",
    "ვ": "в", "ზ": "з", "თ": "т", "ი": "и", "კ": "к",
    "ლ": "л", "მ": "м", "ნ": "н", "ო": "о", "პ": "п",
    "ჟ": "ж", "რ": "р", "ს": "с", "ტ": "т", "უ": "у",
    "ფ": "п", "ქ": "к", "ღ": "г", "ყ": "кх", "შ": "ш",
    "ჩ": "ч", "ც": "ц", "ძ": "дз", "წ": "ц", "ჭ": "ч",
    "ხ": "х", "ჯ": "дж", "ჰ": "х",
}

# Транслитерация грузинских букв → английская латиница
TRANSLIT_EN = {
    "ა": "a", "ბ": "b", "გ": "g", "დ": "d", "ე": "e",
    "ვ": "v", "ზ": "z", "თ": "t", "ი": "i", "კ": "k'",
    "ლ": "l", "მ": "m", "ნ": "n", "ო": "o", "პ": "p'",
    "ჟ": "zh", "რ": "r", "ს": "s", "ტ": "t'", "უ": "u",
    "ფ": "p", "ქ": "k", "ღ": "gh", "ყ": "q", "შ": "sh",
    "ჩ": "ch", "ც": "ts", "ძ": "dz", "წ": "ts'", "ჭ": "ch'",
    "ხ": "kh", "ჯ": "j", "ჰ": "h",
}

# Слоги — гласные
VOWELS_GE = set("აეიოუ")


def is_complete_georgian_translation(text: str) -> bool:
    """Return True only for non-empty text whose letters are all Georgian."""
    if not text or not text.strip():
        return False

    has_georgian_letter = False
    for char in text:
        if char in TRANSLIT_RU:
            has_georgian_letter = True
        elif char.isalpha():
            return False
    return has_georgian_letter


def _transliterate(text: str, table: dict) -> str:
    """Транслитерация по таблице."""
    result = []
    for char in text:
        result.append(table.get(char, char))
    return "".join(result)


def _split_hint_word(word: str) -> list[str]:
    """Split one Georgian word and keep its final consonants in the last syllable."""
    syllables = []
    current = []

    for char in word:
        current.append(char)
        if char in VOWELS_GE:
            syllables.append("".join(current))
            current = []

    if current:
        tail = "".join(current)
        if syllables:
            syllables[-1] += tail
        else:
            syllables.append(tail)

    return syllables


def _bracket_hint_word(word: str, table: dict) -> str:
    syllables = _split_hint_word(word)
    return "[" + "-".join(_transliterate(syllable, table) for syllable in syllables) + "]"


async def translate_to_georgian(text: str) -> str:
    """Перевод текста на грузинский."""
    text_stripped = text.strip()
    if not text_stripped:
        raise TranslationError("Не удалось перевести фразу целиком")
    dictionary_key = text_stripped.strip(SOURCE_EDGE_PUNCTUATION).lower()
    
    # 1. Точное совпадение фразы в словаре
    if dictionary_key in DICTIONARY:
        candidate = DICTIONARY[dictionary_key]
        if not is_complete_georgian_translation(candidate):
            raise TranslationError("Не удалось перевести фразу целиком")
        return candidate
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise TranslationUnavailableError("Сервис перевода сейчас недоступен")

    try:
        async with asyncio.timeout(GEMINI_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    GEMINI_URL,
                    headers={"x-goog-api-key": api_key},
                    json={
                        "systemInstruction": {
                            "parts": [{"text": "Translate the entire Russian phrase into natural Georgian. Return only the complete Georgian translation, with no explanations or markdown."}]
                        },
                        "contents": [{"role": "user", "parts": [{"text": text_stripped}]}],
                        "generationConfig": {"temperature": 0},
                    },
                )
                response.raise_for_status()
                response_data = response.json()
    except Exception as error:
        logger.warning("Gemini translation failed: errorClass=%s", type(error).__name__)
        raise TranslationUnavailableError("Сервис перевода сейчас недоступен") from None

    try:
        candidate_response = response_data["candidates"][0]
        if candidate_response["finishReason"] != "STOP":
            raise ValueError("Gemini response did not finish")
        parts = candidate_response["content"]["parts"]
        candidate = "".join(part["text"] for part in parts if not part.get("thought")).strip()
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        logger.warning("Gemini returned an incomplete response")
        raise TranslationError("Не удалось перевести фразу целиком") from None

    if not is_complete_georgian_translation(candidate):
        logger.warning("Gemini returned an incomplete or mixed-script result")
        raise TranslationError("Не удалось перевести фразу целиком")

    return candidate


def transliterate_georgian(text: str) -> str:
    """Русская транслитерация грузинского текста."""
    return _transliterate(text, TRANSLIT_RU)


def _transliterate_hint(text: str, table: dict) -> str:
    """Bracket Georgian runs word by word, leaving punctuation in place."""
    words = []
    for word in text.split():
        parts = []
        current = []
        for char in word:
            if char in TRANSLIT_RU:
                current.append(char)
            else:
                if current:
                    parts.append(_bracket_hint_word("".join(current), table))
                    current = []
                parts.append(char)
        if current:
            parts.append(_bracket_hint_word("".join(current), table))
        words.append("".join(parts))
    return " ".join(words)


def transliterate_syllables(text: str) -> str:
    """Russian syllable hint with independent bracketed words."""
    return _transliterate_hint(text, TRANSLIT_RU)


def transliterate_english(text: str) -> str:
    """Английская транслитерация грузинского текста."""
    return _transliterate(text, TRANSLIT_EN)


def transliterate_english_syllables(text: str) -> str:
    """English syllable hint with independent bracketed words."""
    return _transliterate_hint(text, TRANSLIT_EN)
