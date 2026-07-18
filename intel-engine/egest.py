import hashlib
import json
import os
import time

OPPORTUNITIES_FILE = "../data/opportunities.jsonl"
SELF_OPPORTUNITIES_FILE = "../data/self_opportunities.jsonl"


def make_id(opp):
    base = (
        opp["buyer"]["original_content"]["message_id"]
        + opp["seller"]["original_content"]["message_id"]
    )
    return hashlib.md5(base.encode()).hexdigest()


def _load_existing_ids(filepath: str) -> set:
    """Lê os IDs já presentes no arquivo para evitar duplicatas no append."""
    existing = set()
    if not os.path.exists(filepath):
        return existing
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                oid = obj.get("id")
                if oid:
                    existing.add(oid)
            except json.JSONDecodeError:
                continue
    return existing


def _export(opportunities, filepath: str) -> int:
    existing_ids = _load_existing_ids(filepath)

    new_count = 0
    with open(filepath, "a", encoding="utf-8") as f:
        for opp in opportunities:
            opp["id"] = make_id(opp)
            opp["timestamp"] = int(time.time())

            if opp["id"] in existing_ids:
                continue

            f.write(json.dumps(opp, ensure_ascii=False) + "\n")
            existing_ids.add(opp["id"])
            new_count += 1

    return new_count


def export_opportunities(opportunities) -> int:
    return _export(opportunities, OPPORTUNITIES_FILE)


def export_self_opportunities(opportunities) -> int:
    """Oportunidades envolvendo imóveis próprios — arquivo separado,
    consumido pelo dispatch de DM prioritária em main.js."""
    return _export(opportunities, SELF_OPPORTUNITIES_FILE)
