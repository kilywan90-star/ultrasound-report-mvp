import unittest

from routers.asr import _looks_invalid_asr


class ASRInvalidFilterTest(unittest.TestCase):
    def test_repeated_medical_phrase_with_replacement_char_is_invalid(self):
        sample = "中孕四维。二十二。到二十五。" + "腹部。" * 80 + "�" + "腹部。" * 20
        self.assertTrue(_looks_invalid_asr(sample))

    def test_repeated_short_phrase_is_invalid(self):
        self.assertTrue(_looks_invalid_asr("腹部。" * 40))

    def test_normal_medical_sentence_is_valid(self):
        sample = "肝脏大小正常，包膜光整，实质回声均匀，胆囊壁光滑。"
        self.assertFalse(_looks_invalid_asr(sample))


if __name__ == "__main__":
    unittest.main()
