import json
import time

from classifier import run_classifier
from cleaner import (
    clean_and_dedup_messages,
    clean_and_dedup_opportunities,
    clean_and_dedup_self_opportunities,
    dedup_dispatch_state,
    reconcile_engine_state,
)
from database import get_property_details
from egest import export_opportunities, export_self_opportunities
from matcher import get_opportunity
from normalizer import run_normalizer, run_self_normalizer

STATE_FILE = "../data/engine_state.json"

# Intervalo entre execuções do cleaner. Não roda a cada iteração do loop
# (a cada 3s) porque cleaner.py reescreve os .jsonl inteiros — caro demais
# pra rodar com essa frequência.
CLEANUP_INTERVAL_SECONDS = 3600  # 1 hora


def load_state():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
            if "seen_hashes" not in state:
                state["seen_hashes"] = []
            return state
    except Exception:
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

    batch_ids = set()
    batch_hashes = set()

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

            id_seen = (msg_id in seen_id_set) or (msg_id in batch_ids)
            hash_seen = (ad_hash in seen_hash_set) or (ad_hash in batch_hashes)

            if id_seen or hash_seen:
                continue

            new_messages.append(msg)

            if msg_id:
                batch_ids.add(msg_id)
            if ad_hash:
                batch_hashes.add(ad_hash)

    return new_messages, all_ids, all_hashes


def run_cleanup():
    print(f"[ENGINE] Rodando limpeza periódica ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    clean_and_dedup_messages()
    clean_and_dedup_opportunities()
    clean_and_dedup_self_opportunities()
    reconcile_engine_state()
    dedup_dispatch_state()


last_cleanup = 0.0

while True:
    state = load_state()

    new_messages, all_ids, all_hashes = read_new_messages(
        state["seen_ids"], state["seen_hashes"]
    )

    if new_messages:
        sellers, buyers, useless = run_classifier(new_messages)
        sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
        self_ads = run_self_normalizer(get_property_details())

        # TEMP (v1.7.0): matching comprador-vendedor regular em standby
        # enquanto testamos a priorização de imóveis próprios.
        # Para reativar: descomente as duas linhas abaixo.
        # opportunities = get_opportunity(sellers_pad, buyers_pad)
        self_opportunities = get_opportunity(self_ads, buyers_pad)

        state["seen_ids"] = all_ids
        state["seen_hashes"] = all_hashes

        save_state(state)

        # if opportunities:
        #     export_opportunities(opportunities)

        if self_opportunities:
            export_self_opportunities(self_opportunities)

        print("Processed:", len(new_messages))

    if time.time() - last_cleanup >= CLEANUP_INTERVAL_SECONDS:
        run_cleanup()
        last_cleanup = time.time()

    time.sleep(3)
