import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from normalizer import NormalizedAd, extract_phone_from_text, is_lid


class NormalizerExtractionTests(unittest.TestCase):
    def test_price_extraction_with_k_suffix(self):
        ad = NormalizedAd("preciso de apartamento no maayan por 800k", "buy")
        res = ad.normalize()
        self.assertEqual(res["price"], 800000)

    def test_price_extraction_with_mil_suffix(self):
        ad = NormalizedAd("busco apartamento no maayan até 800 mil", "buy")
        res = ad.normalize()
        self.assertEqual(res["price"], 800000)

    def test_price_extraction_with_million_m_suffix(self):
        ad = NormalizedAd("preciso de opcao em ipanema 65m2 1.8M", "buy")
        res = ad.normalize()
        self.assertEqual(res["price"], 1800000)

    def test_condominium_parent_neighborhood_resolution(self):
        ad = NormalizedAd("preciso de apartamento no maayan por 800k", "buy")
        res = ad.normalize()
        self.assertIn("MAAYAN", res["neighborhood"])
        self.assertIn("BARRA OLIMPICA", res["neighborhood"])
        self.assertEqual(res["sub_neighborhood"], "MAAYAN")
        self.assertEqual(res["property_type"], "APARTAMENTO")

    def test_phone_extraction_from_message_text(self):
        text1 = "Falar com Marcelo no (21) 98765-4321 direto"
        self.assertEqual(extract_phone_from_text(text1), "5521987654321")

        text2 = "Chame no wa.me/5521998887766 agora"
        self.assertEqual(extract_phone_from_text(text2), "5521998887766")

        text3 = "Opção direta Tel 21999998888"
        self.assertEqual(extract_phone_from_text(text3), "5521999998888")

    def test_is_lid_detection(self):
        self.assertTrue(is_lid("173680541884580@lid"))
        self.assertTrue(is_lid("173680541884580"))
        self.assertTrue(is_lid("Desconhecido"))
        self.assertTrue(is_lid(None))
        self.assertFalse(is_lid("5521999998888"))
        self.assertFalse(is_lid("21999998888"))


if __name__ == "__main__":
    unittest.main()
