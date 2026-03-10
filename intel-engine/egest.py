import json
import hashlib
import time


def make_id(opp):
    base = (
        opp["buyer"]["original_content"]["message_id"]
        + opp["seller"]["original_content"]["message_id"]
    )
    return hashlib.md5(base.encode()).hexdigest()


def export_opportunities(opportunities):
    with open("../data/opportunities.jsonl", "a", encoding="utf-8") as f:
        for opp in opportunities:
            opp["id"] = make_id(opp)
            opp["timestamp"] = int(time.time())
            f.write(json.dumps(opp, ensure_ascii=False) + "\n")