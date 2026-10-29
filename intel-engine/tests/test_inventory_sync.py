import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inventory_sync import classify_diff, fingerprint_property, sync_inventory
from inventory_sync_worker import run_worker
import threading


def prop(property_id=1, **overrides):
    item = {
        "property_id": property_id,
        "property_type": "Apartamento",
        "bedrooms": 3,
        "parking_spots": 2,
        "price": Decimal("750000.00"),
        "area": Decimal("110.0"),
        "sun_type": "Nascente",
        "neighborhood": "Pituba",
        "status": "available",
        "description": "Synthetic property",
    }
    item.update(overrides)
    return item


class State:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.saved = []
        self.missing = []

    def load(self):
        return self.rows

    def save_present(self, item, fingerprint):
        self.saved.append((item["property_id"], fingerprint, item["status"]))
        self.rows[item["property_id"]] = {
            "property_id": item["property_id"],
            "fingerprint": fingerprint,
            "source_status": item["status"],
            "is_present": True,
        }

    def save_missing(self, property_id):
        self.missing.append(property_id)
        self.rows[property_id]["is_present"] = False


class Graph:
    def __init__(self, fail=False):
        self.projected = []
        self.deactivated = []
        self.fail = fail

    def ingest_ad(self, ad):
        if self.fail:
            raise RuntimeError("Neo4j unavailable")
        self.projected.append(ad)

    def deactivate_inventory_property(self, property_id):
        self.deactivated.append(property_id)


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_is_deterministic_and_numeric_normalized(self):
        first = prop()
        second = dict(reversed(list(first.items())))
        second["price"] = Decimal("750000")
        second["area"] = 110.0
        self.assertEqual(fingerprint_property(first), fingerprint_property(second))

    def test_relevant_change_changes_fingerprint(self):
        self.assertNotEqual(
            fingerprint_property(prop()),
            fingerprint_property(prop(price=Decimal("760000"))),
        )

    def test_irrelevant_external_field_does_not_change_fingerprint(self):
        self.assertEqual(
            fingerprint_property(prop()),
            fingerprint_property(prop(linkpublico="external-only")),
        )


class DiffTests(unittest.TestCase):
    def test_empty_state_classifies_all_as_new(self):
        diff = classify_diff([prop(1), prop(2), prop(3)], {})
        self.assertEqual(len(diff["new"]), 3)

    def test_same_snapshot_is_unchanged(self):
        item = prop()
        state = {1: {"fingerprint": fingerprint_property(item), "is_present": True}}
        diff = classify_diff([item], state)
        self.assertEqual(len(diff["unchanged"]), 1)

    def test_missing_and_reappeared_are_distinguished(self):
        item = prop()
        state = {
            1: {"fingerprint": fingerprint_property(item), "is_present": True},
            2: {"fingerprint": "old", "is_present": False},
        }
        diff = classify_diff([prop(2)], state)
        self.assertEqual([row["property_id"] for row in diff["missing"]], [1])
        self.assertEqual([row["property_id"] for row in diff["reappeared"]], [2])


class SyncTests(unittest.TestCase):
    def test_sync_projects_new_and_does_not_reproject_unchanged(self):
        state = State()
        graph = Graph()
        first = sync_inventory(lambda: [prop(1), prop(2), prop(3)], state, graph)
        second = sync_inventory(lambda: [prop(1), prop(2), prop(3)], state, graph)
        self.assertEqual(first["new"], 3)
        self.assertEqual(second["unchanged"], 3)
        self.assertEqual(len(graph.projected), 3)

    def test_status_change_is_projected_as_unavailable(self):
        item = prop()
        state = State({1: {"fingerprint": fingerprint_property(item), "is_present": True}})
        graph = Graph()
        summary = sync_inventory(lambda: [prop(status="unavailable")], state, graph)
        self.assertEqual(summary["changed"], 1)
        self.assertEqual(graph.projected[0]["status"], "unavailable")

    def test_missing_deactivates_without_deleting_property(self):
        item = prop()
        state = State({1: {"fingerprint": fingerprint_property(item), "is_present": True}})
        graph = Graph()
        summary = sync_inventory(lambda: [], state, graph)
        self.assertEqual(summary["missing"], 1)
        self.assertEqual(graph.deactivated, [1])
        self.assertEqual(state.missing, [1])

    def test_reappeared_is_reprojected_and_marked_present(self):
        item = prop()
        state = State({1: {"fingerprint": "old", "is_present": False}})
        graph = Graph()
        summary = sync_inventory(lambda: [item], state, graph)
        self.assertEqual(summary["reappeared"], 1)
        self.assertEqual(len(graph.projected), 1)
        self.assertTrue(state.rows[1]["is_present"])

    def test_force_rebuild_reprojects_unchanged_properties(self):
        item = prop()
        state = State({1: {"fingerprint": fingerprint_property(item), "is_present": True}})
        graph = Graph()
        summary = sync_inventory(lambda: [item], state, graph, force=True)
        self.assertEqual(summary["changed"], 1)
        self.assertEqual(len(graph.projected), 1)

    def test_source_failure_does_not_mark_missing(self):
        item = prop()
        state = State({1: {"fingerprint": fingerprint_property(item), "is_present": True}})
        graph = Graph()

        def failed_snapshot():
            raise RuntimeError("PostgreSQL unavailable")

        with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
            sync_inventory(failed_snapshot, state, graph)
        self.assertEqual(state.missing, [])

    def test_neo4j_failure_does_not_advance_state(self):
        with self.assertRaisesRegex(RuntimeError, "Neo4j"):
            sync_inventory(lambda: [prop()], State(), Graph(fail=True))


class EngineDecouplingTests(unittest.TestCase):
    def test_message_processor_does_not_load_inventory(self):
        source = Path(__file__).resolve().parents[1].joinpath("engine.py").read_bytes().decode("utf-8", errors="ignore")
        process_source = source.split("def main():", 1)[0]
        self.assertNotIn("get_property_details", process_source)
        self.assertNotIn("get_inventory_snapshot", process_source)
        self.assertNotIn("sync_inventory", process_source)


class WorkerTests(unittest.TestCase):
    def test_worker_runs_immediately_then_waits_without_overlap(self):
        stop_event = threading.Event()
        calls = []
        active = 0
        maximum = 0

        def run_once():
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            calls.append("sync")
            active -= 1

        def sleep(_interval):
            calls.append("wait")
            if len(calls) == 2:
                stop_event.set()

        run_worker(run_once, 300, stop_event, sleep=sleep)
        self.assertEqual(calls, ["sync", "wait"])
        self.assertEqual(maximum, 1)

    def test_worker_survives_transient_failure_and_retries(self):
        stop_event = threading.Event()
        attempts = []

        def run_once():
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("temporary")

        def sleep(_interval):
            if len(attempts) == 2:
                stop_event.set()

        run_worker(run_once, 1, stop_event, sleep=sleep)
        self.assertEqual(len(attempts), 2)

    def test_worker_shutdown_before_start_runs_no_cycle(self):
        stop_event = threading.Event()
        stop_event.set()
        calls = []
        run_worker(lambda: calls.append(1), 1, stop_event, sleep=lambda _: None)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
