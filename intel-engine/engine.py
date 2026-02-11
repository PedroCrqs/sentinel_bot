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
        return {"last_line": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def read_new_messages(start):
    with open("../data/messages.jsonl", encoding="utf-8") as f:
        lines = f.readlines()
    return lines[start:], len(lines)


while True:

    state = load_state()

    new_lines, total = read_new_messages(state["last_line"])

    if new_lines:

        messages = [json.loads(l) for l in new_lines]

        sellers, buyers = run_classifier(messages)
        sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
        opportunities = get_opportunity(sellers_pad, buyers_pad)

        if opportunities:
            export_opportunities(opportunities)

        state["last_line"] = total
        save_state(state)

        print("Processed:", len(messages))

    time.sleep(3)

#  ================  DEBUG ==================

# messages = []

# with open("data/messages.jsonl", encoding="utf-8") as f:
#     lines = f.readlines()

# messages = [json.loads(l) for l in lines]

# sellers, buyers = run_classifier(messages)
# sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
# opportunities = get_opportunity(sellers_pad, buyers_pad)

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
