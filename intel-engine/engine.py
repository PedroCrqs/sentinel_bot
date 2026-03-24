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
            return json.load(f)
    except:
        return {"seen_ids": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def read_new_messages(seen_ids):
    seen_set = set(seen_ids)
    new_messages = []
    all_ids = []

    with open("../data/messages.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            msg_id = msg.get("message_id")
            if msg_id:
                all_ids.append(msg_id)
                if msg_id not in seen_set:
                    new_messages.append(msg)

    return new_messages, all_ids


while True:

    state = load_state()

    new_messages, all_ids = read_new_messages(state["seen_ids"])

    if new_messages:

        sellers, buyers, useless = run_classifier(new_messages)
        sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
        opportunities = get_opportunity(sellers_pad, buyers_pad)

        if opportunities:
            export_opportunities(opportunities)

        state["seen_ids"] = all_ids
        save_state(state)

        print("Processed:", len(new_messages))

    time.sleep(3)

#  ================  DEBUG ==================

# messages = []

# with open("../data/messages.jsonl", encoding="utf-8") as f:
#     lines = f.readlines()

# messages = [json.loads(l) for l in lines]

# sellers, buyers, useless = run_classifier(messages)
# sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
# opportunities = get_opportunity(sellers_pad, buyers_pad)

# for u in useless:
#     print(f"{u.data['message']}\n")

# for opp in opportunities:
#     print(f"\n{'='*80}")
#     print(f"SCORE: {opp['score']}")
#     print(f"\nCOMPRADOR:")
#     print(f"  Mensagem: {opp['buyer']['raw_text']}...")
#     print(f"  Bairro: {opp['buyer']['neighborhood']}")
#     print(f"  Preço máx: {opp['buyer']['price']}")
#     print(f"  Quartos mín: {opp['buyer']['bedrooms']}")
#     print(f"  Área mín: {opp['buyer']['area_m2']}")
#     print(f"\nVENDEDOR:")
#     print(f"  Mensagem: {opp['seller']['raw_text']}...")
#     print(f"  Bairro: {opp['seller']['neighborhood']}")
#     print(f"  Preço: {opp['seller']['price']}")
#     print(f"  Quartos: {opp['seller']['bedrooms']}")
#     print(f"  Área: {opp['seller']['area_m2']}")
#     print(f"{'='*80}")


#  ================  DEBUG ==================

# messages = []

# with open("../data/messages.jsonl", encoding="utf-8") as f:
#     lines = f.readlines()

# messages = [json.loads(l) for l in lines]

# sellers, buyers, useless = run_classifier(messages)
# sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
# opportunities = get_opportunity(sellers_pad, buyers_pad)

# for u in useless:
#     print(f"{u.data['message']}\n")

# for opp in opportunities:
#     print(f"\n{'='*80}")
#     print(f"SCORE: {opp['score']}")
#     print(f"\nCOMPRADOR:")
#     print(f"  Mensagem: {opp['buyer']['raw_text']}...")
#     print(f"  Bairro: {opp['buyer']['neighborhood']}")
#     print(f"  Preço máx: {opp['buyer']['price']}")
#     print(f"  Quartos mín: {opp['buyer']['bedrooms']}")
#     print(f"  Área mín: {opp['buyer']['area_m2']}")
#     print(f"\nVENDEDOR:")
#     print(f"  Mensagem: {opp['seller']['raw_text']}...")
#     print(f"  Bairro: {opp['seller']['neighborhood']}")
#     print(f"  Preço: {opp['seller']['price']}")
#     print(f"  Quartos: {opp['seller']['bedrooms']}")
#     print(f"  Área: {opp['seller']['area_m2']}")
#     print(f"{'='*80}")
