import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inventory_adapter import InventoryAdapterError, map_inventory_row


def inventory_row(**overrides):
    row = {
        "imovelid": 42,
        "tipologia": "Apartamento",
        "quartos": 3,
        "vagas": 2,
        "valor": 750000,
        "metragem": 110,
        "sol": "Nascente",
        "bairroid": 7,
        "bairro_nome": "Pituba",
        "imovelstatus": "Disponível",
        "descricao": "Synthetic inventory row",
        "datacadastro": None,
    }
    row.update(overrides)
    return row


class InventoryAdapterTests(unittest.TestCase):
    def test_maps_complete_external_row(self):
        mapped = map_inventory_row(inventory_row())

        self.assertEqual(mapped["property_id"], 42)
        self.assertEqual(mapped["property_type"], "Apartamento")
        self.assertEqual(mapped["bedrooms"], 3)
        self.assertEqual(mapped["parking_spots"], 2)
        self.assertEqual(mapped["price"], 750000)
        self.assertEqual(mapped["area"], 110)
        self.assertEqual(mapped["sun_type"], "Nascente")
        self.assertEqual(mapped["neighborhood"], "Pituba")
        self.assertEqual(mapped["status"], "available")

    def test_preserves_optional_missing_values_as_none(self):
        mapped = map_inventory_row(
            inventory_row(vagas=None, sol=None, descricao=None, datacadastro=None)
        )

        self.assertIsNone(mapped["parking_spots"])
        self.assertIsNone(mapped["sun_type"])
        self.assertIsNone(mapped["description"])

    def test_invalid_neighborhood_fails_without_unknown_fallback(self):
        with self.assertRaisesRegex(InventoryAdapterError, "bairroid/bairros.nome"):
            map_inventory_row(inventory_row(bairro_nome=None))

    def test_missing_neighborhood_id_lookup_fails_explicitly(self):
        with self.assertRaisesRegex(InventoryAdapterError, "bairroid"):
            map_inventory_row(inventory_row(bairroid=None, bairro_nome=None))

    def test_unavailable_status_is_not_available(self):
        mapped = map_inventory_row(inventory_row(imovelstatus="Vendido"))

        self.assertEqual(mapped["status"], "unavailable")

    def test_unknown_status_fails_explicitly(self):
        with self.assertRaisesRegex(InventoryAdapterError, "Unknown inventory status"):
            map_inventory_row(inventory_row(imovelstatus="???"))


if __name__ == "__main__":
    unittest.main()
