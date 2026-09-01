"""Long-running PM2 worker for periodic inventory snapshot/diff sync."""

from __future__ import annotations

import logging
import signal
import threading

from inventory_sync import InventorySyncStateRepository, sync_inventory
from runtime_config import inventory_sync_enabled, inventory_sync_interval_seconds

LOGGER = logging.getLogger(__name__)


def run_worker(run_once, interval_seconds, stop_event, sleep=None):
    """Run synchronously, immediately and once per interval until stopped."""
    wait = sleep or stop_event.wait
    while not stop_event.is_set():
        try:
            run_once()
        except Exception as exc:
            LOGGER.error("inventory sync failed: %s", type(exc).__name__)
        if not stop_event.is_set():
            LOGGER.info("next sync in %ss", interval_seconds)
            wait(interval_seconds)


def sync_once():
    from database import get_inventory_snapshot
    from graphs.neo4j_client import GraphClient

    graph = GraphClient()
    try:
        return sync_inventory(get_inventory_snapshot, InventorySyncStateRepository(), graph)
    finally:
        graph.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not inventory_sync_enabled():
        LOGGER.info("inventory sync worker disabled")
        return

    stop_event = threading.Event()

    def request_shutdown(signum, _frame):
        LOGGER.info("inventory sync worker stopping signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    interval = inventory_sync_interval_seconds()
    LOGGER.info("inventory sync worker started interval=%ss", interval)
    run_worker(sync_once, interval, stop_event)
    LOGGER.info("inventory sync worker stopped")


if __name__ == "__main__":
    main()
