import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path


ENGINE_PATH = Path(__file__).resolve().parents[1] / "engine.py"


class DeliveryDependencies:
    message = {"message_id": "m-1", "status": "PENDING"}
    opportunities = []
    graph_error = None
    save_error = None
    publish_error = None
    calls = []


class FakeChannel:
    def __init__(self):
        self.acks = []
        self.nacks = []
        self.published = []

    def basic_ack(self, delivery_tag):
        self.acks.append(delivery_tag)
        DeliveryDependencies.calls.append("ack")

    def basic_nack(self, delivery_tag, requeue):
        self.nacks.append((delivery_tag, requeue))
        DeliveryDependencies.calls.append("nack")

    def basic_publish(self, **kwargs):
        if DeliveryDependencies.publish_error:
            raise DeliveryDependencies.publish_error
        self.published.append(kwargs)
        DeliveryDependencies.calls.append("publish")


class FakeMethod:
    delivery_tag = 7


class EngineDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_modules = {
            name: sys.modules.get(name)
            for name in ("database", "classifier", "normalizer", "runtime_config", "graphs", "graphs.neo4j_client")
        }

        database = types.ModuleType("database")
        database.get_message_by_id = lambda message_id: DeliveryDependencies.message

        def save_opportunities(opportunities):
            if DeliveryDependencies.save_error:
                raise DeliveryDependencies.save_error
            DeliveryDependencies.calls.append("save")
            return [101] if opportunities else []

        def update_message_status(message_id, status, normalized_data=None):
            DeliveryDependencies.calls.append("processed")

        database.save_opportunities = save_opportunities
        database.update_message_status = update_message_status

        classifier = types.ModuleType("classifier")
        classifier.run_classifier = lambda messages: ([], [{"original_content": {"message_id": "m-1"}}], [])
        normalizer = types.ModuleType("normalizer")
        normalizer.run_normalizer = lambda sellers, buyers: (sellers, buyers)

        class FakeGraph:
            def __init__(self):
                DeliveryDependencies.calls.append("graph")

            def ingest_ad(self, ad):
                if DeliveryDependencies.graph_error:
                    raise DeliveryDependencies.graph_error

            def match_opportunities(self):
                if DeliveryDependencies.graph_error:
                    raise DeliveryDependencies.graph_error
                return DeliveryDependencies.opportunities

            def close(self):
                DeliveryDependencies.calls.append("close")

        graphs = types.ModuleType("graphs")
        graphs.__path__ = []
        neo4j = types.ModuleType("graphs.neo4j_client")
        neo4j.GraphClient = FakeGraph
        runtime_config = types.ModuleType("runtime_config")
        runtime_config.rabbitmq_url = lambda: "amqp://test"

        for name, module in {
            "database": database,
            "classifier": classifier,
            "normalizer": normalizer,
            "runtime_config": runtime_config,
            "graphs": graphs,
            "graphs.neo4j_client": neo4j,
        }.items():
            sys.modules[name] = module

        spec = importlib.util.spec_from_file_location("engine_delivery_under_test", ENGINE_PATH)
        cls.engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.engine)

    @classmethod
    def tearDownClass(cls):
        for name, module in cls.original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def setUp(self):
        DeliveryDependencies.message = {"message_id": "m-1", "status": "PENDING"}
        DeliveryDependencies.opportunities = []
        DeliveryDependencies.graph_error = None
        DeliveryDependencies.save_error = None
        DeliveryDependencies.publish_error = None
        DeliveryDependencies.calls = []
        self.channel = FakeChannel()

    def deliver(self, message_id="m-1"):
        return self.engine.on_message(
            self.channel,
            FakeMethod(),
            None,
            json.dumps({"message_id": message_id}).encode(),
        )

    def test_zero_opportunities_is_success(self):
        self.assertTrue(self.deliver())
        self.assertEqual(self.channel.acks, [7])
        self.assertEqual(self.channel.nacks, [])
        self.assertIn("processed", DeliveryDependencies.calls)

    def test_graph_failure_is_requeued_and_not_processed(self):
        DeliveryDependencies.graph_error = RuntimeError("neo4j unavailable")
        self.assertFalse(self.deliver())
        self.assertEqual(self.channel.acks, [])
        self.assertEqual(self.channel.nacks, [(7, True)])
        self.assertNotIn("processed", DeliveryDependencies.calls)

    def test_save_failure_is_requeued(self):
        DeliveryDependencies.opportunities = [{"opportunity_id": "o-1"}]
        DeliveryDependencies.save_error = RuntimeError("postgres unavailable")
        self.assertFalse(self.deliver())
        self.assertEqual(self.channel.acks, [])
        self.assertEqual(self.channel.nacks, [(7, True)])

    def test_publish_failure_is_requeued_before_processed(self):
        DeliveryDependencies.opportunities = [{"opportunity_id": "o-1"}]
        DeliveryDependencies.publish_error = RuntimeError("publish failed")
        self.assertFalse(self.deliver())
        self.assertEqual(self.channel.acks, [])
        self.assertEqual(self.channel.nacks, [(7, True)])
        self.assertNotIn("processed", DeliveryDependencies.calls)

    def test_processed_redelivery_is_acked_without_side_effects(self):
        DeliveryDependencies.message = {"message_id": "m-1", "status": "PROCESSED"}
        self.assertTrue(self.deliver())
        self.assertEqual(self.channel.acks, [7])
        self.assertEqual(self.channel.nacks, [])
        self.assertEqual(DeliveryDependencies.calls, ["ack"])

    def test_missing_message_is_requeued(self):
        DeliveryDependencies.message = None
        self.assertFalse(self.deliver())
        self.assertEqual(self.channel.acks, [])
        self.assertEqual(self.channel.nacks, [(7, True)])

    def test_success_effects_precede_ack(self):
        DeliveryDependencies.opportunities = [{"opportunity_id": "o-1"}]
        self.assertTrue(self.deliver())
        self.assertEqual(DeliveryDependencies.calls, ["graph", "close", "save", "publish", "processed", "ack"])


if __name__ == "__main__":
    unittest.main()
