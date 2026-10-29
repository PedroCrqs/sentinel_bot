import os
import time
import unittest

from dotenv import load_dotenv

from pathlib import Path


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import ConstraintError

    NEO4J_DRIVER_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    GraphDatabase = None
    ConstraintError = None
    NEO4J_DRIVER_AVAILABLE = False


@unittest.skipUnless(
    os.getenv("RUN_NEO4J_INTEGRATION") == "1" and NEO4J_DRIVER_AVAILABLE,
    "set RUN_NEO4J_INTEGRATION=1 and install the neo4j Python driver",
)
class Neo4jIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.constraint_error = ConstraintError
        cls.driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
        cls.driver.verify_connectivity()

    @classmethod
    def tearDownClass(cls):
        cls.driver.close()

    def test_duplicate_canonical_person_identity_is_rejected(self):
        person_id = f"integration-test:{time.time_ns()}"
        try:
            with self.driver.session() as session:
                session.run(
                    "MERGE (p:Pessoa {person_id: $person_id})",
                    person_id=person_id,
                ).consume()
                with self.assertRaises(self.constraint_error):
                    session.run(
                        "CREATE (p:Pessoa {person_id: $person_id})",
                        person_id=person_id,
                    ).consume()
        finally:
            with self.driver.session() as session:
                session.run(
                    "MATCH (p:Pessoa {person_id: $person_id}) DELETE p",
                    person_id=person_id,
                ).consume()


if __name__ == "__main__":
    unittest.main()
