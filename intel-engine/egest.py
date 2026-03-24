import json
import hashlib
import time
import os

OPPORTUNITIES_FILE = "../data/opportunities.jsonl"


def make_id(opp):
    base = (
        opp["buyer"]["original_content"]["message_id"]
        + opp["seller"]["original_content"]["message_id"]
    )
    return hashlib.md5(base.encode()).hexdigest()


def _load_existing_ids() -> set:
    """Lê os IDs já presentes no arquivo para evitar duplicatas no append."""
    existing = set()
    if not os.path.exists(OPPORTUNITIES_FILE):
        return existing
    with open(OPPORTUNITIES_FILE, "r", encoding="utf-8") as f:
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


def export_opportunities(opportunities):
    existing_ids = _load_existing_ids()

    new_count = 0
    with open(OPPORTUNITIES_FILE, "a", encoding="utf-8") as f:
        for opp in opportunities:
            opp["id"] = make_id(opp)
            opp["timestamp"] = int(time.time())

            if opp["id"] in existing_ids:
                continue

            f.write(json.dumps(opp, ensure_ascii=False) + "\n")
            existing_ids.add(opp["id"])
            new_count += 1

    return new_count
