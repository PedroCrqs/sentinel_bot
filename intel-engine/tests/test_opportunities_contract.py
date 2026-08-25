import unittest
import importlib
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "001_align_opportunities_contract.sql"
DATABASE_MODULE = ROOT / "intel-engine" / "database.py"
EGRESS_MODULE = ROOT / "wpp-egress" / "main.js"


class FakeCursor:
    def __init__(self):
        self.executions = []
        self.seen_keys = set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        self.executions.append((query, params))
        self.current_key = (params[0], params[1])

    def fetchone(self):
        if self.current_key in self.seen_keys:
            return None
        self.seen_keys.add(self.current_key)
        return (123,)


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        pass


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def getconn(self):
        return self.connection

    def putconn(self, connection):
        pass


class OpportunitiesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.database_source = DATABASE_MODULE.read_text(encoding="utf-8")
        cls.egress_source = EGRESS_MODULE.read_text(encoding="utf-8")

    def test_migration_is_additive_and_idempotent(self):
        sql = self.migration.upper()

        self.assertIn("ALTER TABLE PUBLIC.OPPORTUNITIES", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS SELLER_MESSAGE_ID", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS MATCH_DETAILS JSONB", sql)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS", sql)
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("TRUNCATE", sql)
        self.assertNotIn("DELETE FROM", sql)

    def test_future_entity_ids_are_nullable_preparation(self):
        sql = self.migration.upper()

        self.assertIn("ADD COLUMN IF NOT EXISTS DEMAND_ID VARCHAR", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS OFFER_ID VARCHAR", sql)
        self.assertIn("RULE_VERSION VARCHAR NOT NULL DEFAULT 'V1'", sql)

    def test_existing_save_contract_matches_migration(self):
        self.assertIn("seller_message_id", self.database_source)
        self.assertIn("match_details", self.database_source)
        self.assertIn(
            "ON CONFLICT (buyer_message_id, seller_message_id)",
            self.database_source,
        )
        self.assertIn("Json(opp)", self.database_source)

    def test_save_opportunities_uses_json_and_database_conflict_contract(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        pool = FakePool(connection)

        with patch("psycopg2.pool.SimpleConnectionPool", return_value=pool):
            sys.modules.pop("database", None)
            database = importlib.import_module("database")
            try:
                opportunity = {
                    "buyer_message_id": "buyer-1",
                    "seller_message_id": "seller-1",
                    "matched_imovel_id": 42,
                    "score": 35,
                    "buyer": {"name": "Buyer"},
                }
                inserted = database.save_opportunities([opportunity, opportunity])
            finally:
                sys.modules.pop("database", None)

        self.assertEqual(inserted, [123])
        query, params = cursor.executions[0]
        self.assertIn(
            "ON CONFLICT (buyer_message_id, seller_message_id)", query
        )
        self.assertIn('"buyer_message_id": "buyer-1"', params[4].getquoted().decode())

    def test_egress_reads_details_and_updates_dispatch(self):
        self.assertIn(
            "SELECT match_details FROM opportunities WHERE opportunity_id = $1",
            self.egress_source,
        )
        self.assertIn(
            "UPDATE opportunities SET dispatch_status = 'SENT'",
            self.egress_source,
        )


if __name__ == "__main__":
    unittest.main()
