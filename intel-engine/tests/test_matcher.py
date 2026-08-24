import sys
import unittest
from pathlib import Path
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep identity tests runnable without requiring a live Neo4j client package.
try:
    import neo4j  # noqa: F401
except ModuleNotFoundError:
    class _Neo4jStub:
        @staticmethod
        def driver(*args, **kwargs):
            raise RuntimeError("Neo4j driver is unavailable in this test process")

    sys.modules["neo4j"] = types.SimpleNamespace(GraphDatabase=_Neo4jStub)

from graphs import neo4j_client


class FakeSession:
    def __init__(self, store):
        self.store = store
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.queries.append((query, params))
        if "MATCH (comprador:Pessoa)" in query:
            return []

        self.store["Pessoa"].setdefault(
            params["person_id"],
            {"nome": params["nome"], "telefone": params["telefone"]},
        ).update(
            {
                "nome": params["nome"],
                "telefone": params["telefone"]
                if params["telefone"] is not None
                else self.store["Pessoa"][params["person_id"]]["telefone"],
            }
        )
        self.store["Mensagem"].setdefault(
            params["msg_id"], {"texto": params["texto"]}
        ).update({"texto": params["texto"], "timestamp": params["ts"]})

        if "MERGE (d:Demanda" in query:
            self.store["Demanda"].setdefault(params["demand_id"], {}).update(
                {
                    "price": params["preco"],
                    "bedrooms": params["quartos"],
                    "status": "ACTIVE",
                }
            )
            self.store["relationships"].update(
                {
                    ("Mensagem", params["msg_id"], "EXPRESSA", "Demanda", params["demand_id"]),
                    ("Pessoa", params["person_id"], "CRIOU", "Demanda", params["demand_id"]),
                }
            )
            self.store["relationships"].update(
                {
                    ("Demanda", params["demand_id"], "BUSCA_EM", "Bairro", bairro)
                    for bairro in params["bairros"]
                }
            )
            self.store["Imovel"].setdefault(params["property_id"], {}).update(
                {"legacy_projection": True, "preco": params["preco"]}
            )
        else:
            self.store["Imovel"].setdefault(params["property_id"], {}).update(
                {"preco": params["preco"], "tipo": params["tipo"]}
            )
            self.store["Oferta"].setdefault(params["offer_id"], {}).update(
                {"price": params["preco"], "status": "ACTIVE"}
            )
            self.store["relationships"].update(
                {
                    ("Mensagem", params["msg_id"], "ORIGINA", "Oferta", params["offer_id"]),
                    ("Pessoa", params["person_id"], "PUBLICOU", "Oferta", params["offer_id"]),
                    ("Oferta", params["offer_id"], "REFERE_SE_A", "Imovel", params["property_id"]),
                }
            )
        return []


class FakeDriver:
    def __init__(self):
        self.store = {
            "Pessoa": {},
            "Mensagem": {},
            "Demanda": {},
            "Oferta": {},
            "Imovel": {},
            "relationships": set(),
        }
        self.sessions = []

    def session(self):
        session = FakeSession(self.store)
        self.sessions.append(session)
        return session

    def close(self):
        pass


def external_ad(person_id="person-1", message_id="message-1", phone="5511"):
    return {
        "original_content": {
            "author_id": person_id,
            "author_name": "Pessoa",
            "author_phone": phone,
            "message_id": message_id,
            "timestamp": 1,
        },
        "intent": "oferece",
        "raw_text": "Vendo apartamento",
        "neighborhood": ["Centro"],
        "property_type": "Apartamento",
        "price": 300000,
    }


def buying_ad(person_id="buyer-1", message_id="demand-1", neighborhoods=None):
    ad = external_ad(person_id, message_id)
    ad.update({
        "intent": "busca",
        "neighborhood": neighborhoods or ["Pituba"],
        "property_type": "Apartamento",
        "price": 800000,
        "bedrooms": 3,
    })
    return ad


class CanonicalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.driver = FakeDriver()
        self.original_driver = neo4j_client.GraphDatabase.driver
        neo4j_client.GraphDatabase.driver = lambda *args, **kwargs: self.driver
        self.client = neo4j_client.GraphClient()

    def tearDown(self):
        self.client.close()
        neo4j_client.GraphDatabase.driver = self.original_driver

    def test_same_person_with_different_messages(self):
        self.client.ingest_ad(external_ad(message_id="message-1"))
        self.client.ingest_ad(external_ad(message_id="message-2"))

        self.assertEqual(len(self.driver.store["Pessoa"]), 1)
        self.assertEqual(len(self.driver.store["Mensagem"]), 2)
        self.assertEqual(len(self.driver.store["Imovel"]), 2)

    def test_same_message_is_idempotent(self):
        ad = external_ad()
        self.client.ingest_ad(ad)
        self.client.ingest_ad(ad)

        self.assertEqual(len(self.driver.store["Pessoa"]), 1)
        self.assertEqual(len(self.driver.store["Mensagem"]), 1)
        self.assertEqual(len(self.driver.store["Imovel"]), 1)

    def test_inventory_property_is_updated_without_duplication(self):
        ad = external_ad(person_id="system:majesto", message_id="self-42", phone=None)
        ad["original_content"].update({"imovel_id": 42, "source": "inventory"})
        self.client.ingest_ad(ad)
        ad["price"] = 350000
        self.client.ingest_ad(ad)

        self.assertEqual(len(self.driver.store["Imovel"]), 1)
        self.assertEqual(self.driver.store["Imovel"][42]["preco"], 350000)

    def test_missing_phone_is_allowed_with_valid_author_id(self):
        ad = external_ad(phone=None)
        self.client.ingest_ad(ad)
        self.assertEqual(len(self.driver.store["Pessoa"]), 1)
        self.assertIsNone(self.driver.store["Pessoa"]["person-1"]["telefone"])

    def test_missing_author_id_fails_before_cypher(self):
        ad = external_ad()
        del ad["original_content"]["author_id"]

        with self.assertRaisesRegex(ValueError, "author_id/Pessoa.person_id"):
            self.client.ingest_ad(ad)

        self.assertEqual(len(self.driver.sessions), 0)

    def test_missing_message_id_fails_before_cypher(self):
        ad = external_ad()
        del ad["original_content"]["message_id"]

        with self.assertRaisesRegex(ValueError, "message_id/Mensagem.id"):
            self.client.ingest_ad(ad)

        self.assertEqual(len(self.driver.sessions), 0)

    def test_missing_inventory_id_fails_without_synthetic_identity(self):
        ad = external_ad(person_id="system:majesto", message_id="self-42", phone=None)
        ad["original_content"]["source"] = "inventory"

        with self.assertRaisesRegex(ValueError, "ImovelID do inventário"):
            self.client.ingest_ad(ad)

        self.assertEqual(len(self.driver.sessions), 0)

    def test_external_property_identity_is_explicitly_provisional(self):
        self.client.ingest_ad(external_ad(message_id="message-9"))
        self.assertIn("message-9_imovel", self.driver.store["Imovel"])

    def test_buying_message_creates_demand_and_direct_location(self):
        self.client.ingest_ad(buying_ad())

        self.assertEqual(len(self.driver.store["Pessoa"]), 1)
        self.assertEqual(len(self.driver.store["Mensagem"]), 1)
        self.assertEqual(len(self.driver.store["Demanda"]), 1)
        self.assertEqual(
            len([
                relation
                for relation in self.driver.store["relationships"]
                if relation[2] == "BUSCA_EM"
            ]),
            1,
        )
        query = self.driver.sessions[-1].queries[0][0]
        self.assertIn("MERGE (m)-[:EXPRESSA]->(d)", query)
        self.assertIn("MERGE (d)-[:BUSCA_EM]->(db)", query)

    def test_buying_message_preserves_multiple_neighborhoods(self):
        self.client.ingest_ad(
            buying_ad(neighborhoods=["Pituba", "Itaigara"])
        )

        locations = [
            relation
            for relation in self.driver.store["relationships"]
            if relation[2] == "BUSCA_EM"
        ]
        self.assertEqual(len(locations), 2)

    def test_selling_message_creates_offer_and_property(self):
        self.client.ingest_ad(external_ad())

        self.assertEqual(len(self.driver.store["Oferta"]), 1)
        self.assertEqual(len(self.driver.store["Imovel"]), 1)
        self.assertIn(
            ("Oferta", "message-1", "REFERE_SE_A", "Imovel", "message-1_imovel"),
            self.driver.store["relationships"],
        )

    def test_same_selling_message_is_one_offer_and_one_property(self):
        ad = external_ad()
        self.client.ingest_ad(ad)
        self.client.ingest_ad(ad)

        self.assertEqual(len(self.driver.store["Oferta"]), 1)
        self.assertEqual(len(self.driver.store["Imovel"]), 1)

    def test_inventory_uses_stable_offer_identity(self):
        ad = external_ad(person_id="system:majesto", message_id="self-42", phone=None)
        ad["original_content"].update({"imovel_id": 42, "source": "inventory"})
        self.client.ingest_ad(ad)
        self.client.ingest_ad(ad)

        self.assertEqual(len(self.driver.store["Oferta"]), 1)
        self.assertIn("self-offer:42", self.driver.store["Oferta"])
        self.assertEqual(len(self.driver.store["Imovel"]), 1)

    def test_matching_compares_person_id(self):
        self.client.match_opportunities()
        query = self.driver.sessions[-1].queries[0][0]
        self.assertIn("comprador.person_id <> vendedor.person_id", query)
        self.assertNotIn("comprador.telefone <> vendedor.telefone", query)


if __name__ == "__main__":
    unittest.main()
