"""Behavioral coverage for Georgian-to-Russian transcription."""

import re
import unittest

from kartuli.translator import (
    DICTIONARY,
    TRANSLIT_RU,
    transliterate_english_syllables,
    transliterate_georgian,
    transliterate_syllables,
)


GEORGIAN_ALPHABET = "აბგდევზთიკლმნოპჟრსტუფქღყშჩცძწჭხჯჰ"
GEORGIAN_CHAR = re.compile(r"[\u10A0-\u10FF]")


class RussianTransliterationTest(unittest.TestCase):
    def test_every_modern_georgian_letter_has_a_russian_mapping(self) -> None:
        self.assertEqual(set(GEORGIAN_ALPHABET), set(TRANSLIT_RU))
        self.assertNotRegex(transliterate_georgian(GEORGIAN_ALPHABET), GEORGIAN_CHAR)

    def test_known_phrase_is_fully_readable_in_russian(self) -> None:
        self.assertEqual(transliterate_georgian("გამარჯობა"), "гамарджоба")
        self.assertEqual(transliterate_georgian("გამარჯობა როგორ"), "гамарджоба рогор")
        self.assertEqual(transliterate_syllables("მადლობა"), "[ма-дло-ба]")

    def test_russian_syllables_keep_word_boundaries_and_final_consonants(self) -> None:
        self.assertEqual(
            transliterate_syllables("გამარჯობა როგორ"),
            "[га-ма-рджо-ба] [ро-гор]",
        )
        self.assertEqual(transliterate_syllables("დამეხმარეთ"), "[да-ме-хма-рет]")
        self.assertEqual(transliterate_syllables("გთხოვთ"), "[гтховт]")

    def test_russian_syllables_keep_punctuation_outside_brackets(self) -> None:
        self.assertEqual(
            transliterate_syllables("გამარჯობა, როგორ ხარ?"),
            "[га-ма-рджо-ба], [ро-гор] [хар]?",
        )
        self.assertEqual(transliterate_syllables("— კარგი"), "— [ка-рги]")
        self.assertEqual(
            transliterate_syllables("«გამარჯობა!» — კარგი"),
            "«[га-ма-рджо-ба]!» — [ка-рги]",
        )

    def test_english_syllables_keep_word_boundaries_and_final_consonants(self) -> None:
        self.assertEqual(
            transliterate_english_syllables("გამარჯობა როგორ"),
            "[ga-ma-rjo-ba] [ro-gor]",
        )
        self.assertEqual(transliterate_english_syllables("დამეხმარეთ"), "[da-me-khma-ret]")
        self.assertEqual(transliterate_english_syllables("გთხოვთ"), "[gtkhovt]")
        self.assertEqual(transliterate_english_syllables("გამარჯობა, როგორ?"), "[ga-ma-rjo-ba], [ro-gor]?")
        self.assertEqual(transliterate_english_syllables("— კარგი"), "— [k'a-rgi]")

    def test_dictionary_outputs_never_leave_georgian_in_russian_transcription(self) -> None:
        for source, translated in DICTIONARY.items():
            with self.subTest(source=source):
                self.assertNotRegex(transliterate_georgian(translated), GEORGIAN_CHAR)
                self.assertNotRegex(transliterate_syllables(translated), GEORGIAN_CHAR)

    def test_taxi_dictionary_key_is_russian(self) -> None:
        self.assertEqual(DICTIONARY["такси"], "ტაქსი")
        self.assertNotIn("таксი", DICTIONARY)


if __name__ == "__main__":
    unittest.main()
