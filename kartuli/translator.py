"""Kartuli-Voice MVP — перевод и транслитерация."""
import logging
import re

logger = logging.getLogger(__name__)

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
    "таксი": "ტაქსი",
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
    "ლ": "л", "მ": "მ", "ნ": "ნ", "ო": "ო", "პ": "პ",
    "ჟ": "ж", "რ": "რ", "ს": "ს", "ტ": "ტ", "უ": "უ",
    "ფ": "ფ", "ქ": "ქ", "ღ": "ღ", "ყ": "ყ", "შ": "შ",
    "ჩ": "ჩ", "ც": "ც", "ძ": "ძ", "წ": "წ", "ჭ": "ჭ",
    "ხ": "ხ", "ჯ": "ჯ", "ჰ": "ჰ",
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


def _transliterate(text: str, table: dict) -> str:
    """Транслитерация по таблице."""
    result = []
    for char in text:
        result.append(table.get(char, char))
    return "".join(result)


def _split_syllables(text: str) -> list[str]:
    """Разбивка грузинского текста на слоги."""
    syllables = []
    current = []
    
    for char in text:
        current.append(char)
        if char in VOWELS_GE:
            syllables.append("".join(current))
            current = []
    
    if current:
        syllables.append("".join(current))
    
    return syllables


async def translate_to_georgian(text: str) -> str:
    """Перевод текста на грузинский."""
    text_stripped = text.strip()
    text_lower = text_stripped.lower()
    
    # 1. Точное совпадение фразы в словаре
    if text_lower in DICTIONARY:
        return DICTIONARY[text_lower]
    
    # 2. Попытка перевода через deep_translator (Google)
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source='ru', target='ka').translate(text_stripped)
        if result and result.strip():
            return result.strip()
    except Exception as e:
        logger.warning(f"Google translate failed: {e}")
    
    # 3. Fallback: перевод по словам
    words = re.split(r'(\s+)', text_lower)
    translated_parts = []
    any_translated = False
    
    for part in words:
        clean = part.strip('.,!?;:')
        if clean in DICTIONARY:
            translated_parts.append(DICTIONARY[clean])
            any_translated = True
        else:
            translated_parts.append(part)
    
    if any_translated:
        return "".join(translated_parts)
    
    return text_stripped


def transliterate_georgian(text: str) -> str:
    """Русская транслитерация грузинского текста."""
    return _transliterate(text, TRANSLIT_RU)


def transliterate_syllables(text: str) -> str:
    """Русская транслитерация по слогам: [да-ме-хма-рет]."""
    syllables = _split_syllables(text)
    result = []
    for s in syllables:
        result.append(_transliterate(s, TRANSLIT_RU))
    return "[" + "-".join(result) + "]"


def transliterate_english(text: str) -> str:
    """Английская транслитерация грузинского текста."""
    return _transliterate(text, TRANSLIT_EN)


def transliterate_english_syllables(text: str) -> str:
    """Английская транслитерация по слогам: [da-me-khma-ret]."""
    syllables = _split_syllables(text)
    result = []
    for s in syllables:
        result.append(_transliterate(s, TRANSLIT_EN))
    return "[" + "-".join(result) + "]"