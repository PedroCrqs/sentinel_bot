"""Snapshot/diff synchronization from the external inventory to Neo4j."""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

LOGGER = logging.getLogger(__name__)
FINGERPRINT_FIELDS = (
    "property_id", "property_type", "bedrooms", "parking_spots", "price",
    "area", "sun_type", "neighborhood", "status", "description",
)


def _canonical_value(value):
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    if isinstance(value, float):
        return _canonical_value(Decimal(str(value)))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def fingerprint_property(property_data: dict) -> str:
    """Hash only canonical fields that affect the inventory projection."""
    payload = {
        field: _canonical_value(property_data.get(field))
        for field in FINGERPRINT_FIELDS
    }
    serialized = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def property_to_inventory_ad(property_data: dict) -> dict:
    """Adapt a canonical property to the inventory graph contract, enriching
    semantic attributes (seafront, nearbeach, condominium, sun_type) from the
    property description via NLP normalization.
    """
    from normalizer import NormalizedAd, canonical_neighborhood, normalize_sun_type

    property_id = property_data["property_id"]
    description = property_data.get("description") or ""

    # Extrai atributos semânticos da coluna descrição utilizando o classificador NLP
    seafront = False
    nearbeach = False
    condominium = False
    extra_neighborhoods = []
    nlp_sun = None

    if description and description.strip():
        try:
            norm_ad = NormalizedAd(description, intent="sell")
            extracted = norm_ad.normalize()
            seafront = bool(extracted.get("seafront", False))
            nearbeach = bool(extracted.get("nearbeach", False))
            condominium = bool(extracted.get("condominium"))
            extra_neighborhoods = extracted.get("neighborhood") or []
            nlp_sun = extracted.get("sun_type")
        except Exception as exc:
            LOGGER.warning("nlp normalization error for property_id=%s: %s", property_id, exc)

    # Normalização canônica do bairro de cadastro (ex: Barra da Tijuca -> BARRA, Recreio -> RECREIO)
    raw_neighborhood = property_data.get("neighborhood") or ""
    canon_neighborhood = canonical_neighborhood(raw_neighborhood)

    # Lista de bairros: canônico como primário, complementado com sub-bairros da descrição
    neighborhoods = [canon_neighborhood]
    for n in extra_neighborhoods:
        if n and n != canon_neighborhood and n not in neighborhoods:
            neighborhoods.append(n)

    # Posição solar: normalizada para MANHA, TARDE, PASSANTE
    raw_sun = property_data.get("sun_type") or nlp_sun
    sun_type = normalize_sun_type(raw_sun)

    return {
        "original_content": {
            "author_name": "Majesto (Imóvel Próprio)",
            "author_id": "system:majesto",
            "author_phone": None,
            "message_id": f"self-{property_id}",
            "timestamp": int(time.time()),
            "imovel_id": property_id,
            "source": "inventory",
        },
        "intent": "oferece",
        "raw_text": description,
        "neighborhood": neighborhoods,
        "property_type": property_data.get("property_type"),
        "price": property_data.get("price"),
        "bedrooms": property_data.get("bedrooms"),
        "area_m2": property_data.get("area"),
        "parking_spots": property_data.get("parking_spots"),
        "seafront": seafront,
        "condominium": condominium,
        "nearbeach": nearbeach,
        "sun_type": sun_type,
        "status": property_data["status"],
    }


def classify_diff(snapshot: list[dict], state: dict, force: bool = False) -> dict:
    """Classify a complete canonical snapshot against state."""
    current = {}
    for item in snapshot:
        property_id = item["property_id"]
        if property_id in current:
            raise ValueError(f"Duplicate property_id in inventory snapshot: {property_id}")
        current[property_id] = item

    diff = {key: [] for key in ("new", "changed", "unchanged", "reappeared", "missing")}
    for property_id, item in current.items():
        old = state.get(property_id)
        if old is None:
            category = "new"
        elif not old["is_present"]:
            category = "reappeared"
        elif old["fingerprint"] != fingerprint_property(item):
            category = "changed"
        else:
            category = "unchanged"
        if force and old is not None and category == "unchanged":
            category = "changed"
        diff[category].append(item)

    for property_id, old in state.items():
        if old["is_present"] and property_id not in current:
            missing = dict(old)
            missing["property_id"] = property_id
            diff["missing"].append(missing)
    return diff


class InventorySyncStateRepository:
    """Persistence boundary for the Sentinel-owned snapshot state."""

    def __init__(self):
        from database import get_db_connection, release_db_connection
        self._get_connection = get_db_connection
        self._release_connection = release_db_connection

    def load(self) -> dict:
        conn = None
        try:
            conn = self._get_connection()
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT property_id, fingerprint, source_status, is_present "
                        "FROM inventory_sync_state"
                    )
                    return {
                        row[0]: {
                            "property_id": row[0], "fingerprint": row[1],
                            "source_status": row[2], "is_present": row[3],
                        }
                        for row in cursor.fetchall()
                    }
        finally:
            self._release_connection(conn)

    def save_present(self, item: dict, fingerprint: str):
        self._execute(
            """
            INSERT INTO inventory_sync_state
                (property_id, fingerprint, source_status, is_present)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (property_id) DO UPDATE SET
                fingerprint = EXCLUDED.fingerprint,
                source_status = EXCLUDED.source_status,
                is_present = TRUE,
                last_synced_at = CURRENT_TIMESTAMP
            """,
            (item["property_id"], fingerprint, item["status"]),
        )

    def save_missing(self, property_id):
        self._execute(
            """
            UPDATE inventory_sync_state
            SET is_present = FALSE, source_status = 'unavailable',
                last_synced_at = CURRENT_TIMESTAMP
            WHERE property_id = %s
            """,
            (property_id,),
        )

    def _execute(self, query, params):
        conn = None
        try:
            conn = self._get_connection()
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                conn.commit()
        finally:
            self._release_connection(conn)


def sync_inventory(snapshot_loader, state_repository, graph_client, force=False) -> dict:
    """Project only changed entries; source failures abort before MISSING."""
    snapshot = snapshot_loader()
    state = state_repository.load()
    diff = classify_diff(snapshot, state, force=force)
    summary = {key: len(value) for key, value in diff.items()}
    summary["total"] = len(snapshot)
    summary["failed"] = 0

    LOGGER.info("inventory sync started")
    for category in ("new", "changed", "reappeared"):
        for item in diff[category]:
            graph_client.ingest_ad(property_to_inventory_ad(item))
            state_repository.save_present(item, fingerprint_property(item))

    for item in diff["missing"]:
        graph_client.deactivate_inventory_property(item["property_id"])
        state_repository.save_missing(item["property_id"])

    LOGGER.info(
        "inventory sync completed total=%d new=%d changed=%d unchanged=%d "
        "reappeared=%d missing=%d failed=%d",
        summary["total"], summary["new"], summary["changed"],
        summary["unchanged"], summary["reappeared"], summary["missing"],
        summary["failed"],
    )
    return summary


def main(argv=None):
    command = (argv or sys.argv[1:] or ["sync"])[0]
    if command not in {"sync", "full", "rebuild", "full-rebuild"}:
        raise SystemExit("Usage: python inventory_sync.py [sync|full-rebuild]")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from database import get_inventory_snapshot
    from graphs.neo4j_client import GraphClient

    graph = GraphClient()
    try:
        return sync_inventory(
            get_inventory_snapshot, InventorySyncStateRepository(), graph,
            force=command != "sync",
        )
    finally:
        graph.close()


if __name__ == "__main__":
    main()
