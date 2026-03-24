import time
import json
from classifier import run_classifier
from normalizer import run_normalizer
from matcher import get_opportunity
from egest import export_opportunities

STATE_FILE = "../data/engine_state.json"


def load_state():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
            if "seen_hashes" not in state:
                state["seen_hashes"] = []
            return state
    except:
        return {"seen_ids": [], "seen_hashes": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def read_new_messages(seen_ids, seen_hashes):
    seen_id_set = set(seen_ids)
    seen_hash_set = set(seen_hashes)

    new_messages = []
    all_ids = []
    all_hashes = []

    with open("../data/messages.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            msg = json.loads(line)
            msg_id = msg.get("message_id")
            ad_hash = msg.get("ad_hash")

            if msg_id:
                all_ids.append(msg_id)

            if ad_hash:
                all_hashes.append(ad_hash)

            # 🔥 FILTRO DUPLO: ID + HASH
            if msg_id not in seen_id_set and ad_hash not in seen_hash_set:
                new_messages.append(msg)

    return new_messages, all_ids, all_hashes


while True:

    state = load_state()

    new_messages, all_ids, all_hashes = read_new_messages(
        state["seen_ids"], state["seen_hashes"]
    )

    if new_messages:

        sellers, buyers, useless = run_classifier(new_messages)
        sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
        opportunities = get_opportunity(sellers_pad, buyers_pad)

        if opportunities:
            export_opportunities(opportunities)

        state["seen_ids"] = all_ids
        state["seen_hashes"] = all_hashes

        save_state(state)

        print("Processed:", len(new_messages))

    time.sleep(3)
