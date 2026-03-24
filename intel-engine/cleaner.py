import json
import time
import os
import hashlib
import re
import unicodedata
from classifier import classify_message

MESSAGES_FILE = "../data/messages.jsonl"
OPPORTUNITIES_FILE = "../data/opportunities.jsonl"
ENGINE_STATE_FILE = "../data/engine_state.json"
DISPATCH_STATE_FILE = "../data/state.json"

THREE_MONTHS = 7_776_000
THIRTY_DAYS = 2_592_000
FIFTEEN_DAYS = 1_296_000


def _normalize_for_hash(text: str) -> str:
    """Mesma lógica do main.js: lowercase, remove acentos via NFD e pontuação."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _compute_ad_hash(message_text: str) -> str:
    return hashlib.md5(_normalize_for_hash(message_text).encode()).hexdigest()


def _load_jsonl(filepath: str):
    """Lê um .jsonl e retorna lista de (linha_raw, objeto_parsed). Ignora linhas inválidas."""
    results = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                results.append((line, json.loads(line)))
            except json.JSONDecodeError:
                results.append((line, None))
    return results


def _write_jsonl(filepath: str, objects: list):
    with open(filepath, "w", encoding="utf-8") as f:
        for obj in objects:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def sync_engine_state(kept_message_ids: list):
    try:
        with open(ENGINE_STATE_FILE) as f:
            state = json.load(f)
    except Exception:
        return

    kept_id_set = set(kept_message_ids)
    state["seen_ids"] = [mid for mid in state.get("seen_ids", []) if mid in kept_id_set]

    with open(ENGINE_STATE_FILE, "w") as f:
        json.dump(state, f)


def sync_engine_state_hashes(kept_hashes: list):
    """Atualiza seen_hashes no engine_state para refletir o que realmente está no arquivo."""
    try:
        with open(ENGINE_STATE_FILE) as f:
            state = json.load(f)
    except Exception:
        return

    state["seen_hashes"] = kept_hashes

    with open(ENGINE_STATE_FILE, "w") as f:
        json.dump(state, f)


def sync_dispatch_state(kept_opp_ids: list):
    try:
        with open(DISPATCH_STATE_FILE) as f:
            state = json.load(f)
    except Exception:
        return

    kept_set = set(kept_opp_ids)
    state["sent"] = {
        oid: v for oid, v in state.get("sent", {}).items() if oid in kept_set
    }

    with open(DISPATCH_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def clean_and_dedup_messages():
    """
    Faz três coisas em uma única passagem sobre messages.jsonl:
      1. Remove mensagens mais antigas que THREE_MONTHS.
      2. Remove mensagens de compradores mais antigas que THIRTY_DAYS.
      3. Remove duplicatas — tanto por message_id quanto por ad_hash.
         - Se o ad_hash não existir no registro, recalcula a partir do texto.
         - Quando há duplicata de conteúdo, mantém a mais recente.
    """
    if not os.path.exists(MESSAGES_FILE):
        return

    now = int(time.time())
    cutoff_3m = now - THREE_MONTHS
    cutoff_30d = now - THIRTY_DAYS

    rows = _load_jsonl(MESSAGES_FILE)

    candidates = []
    removed_age = 0
    removed_buyer_age = 0

    for raw, obj in rows:
        if obj is None:
            continue

        ts = obj.get("timestamp", 0)

        if ts < cutoff_3m:
            removed_age += 1
            continue

        classification = classify_message(obj)
        if classification == "buying" and ts < cutoff_30d:
            removed_buyer_age += 1
            continue

        candidates.append(obj)

    by_id: dict[str, dict] = {}
    for obj in candidates:
        mid = obj.get("message_id")
        if not mid:
            by_id[id(obj)] = obj
            continue
        existing = by_id.get(mid)
        if existing is None or obj.get("timestamp", 0) > existing.get("timestamp", 0):
            by_id[mid] = obj

    by_hash: dict[str, dict] = {}
    for obj in by_id.values():
        ad_hash = obj.get("ad_hash")
        if not ad_hash:
            msg_text = obj.get("message", "")
            ad_hash = _compute_ad_hash(msg_text) if msg_text else None

        if not ad_hash:
            by_hash[obj.get("message_id", str(id(obj)))] = obj
            continue

        existing = by_hash.get(ad_hash)
        if existing is None or obj.get("timestamp", 0) > existing.get("timestamp", 0):
            by_hash[ad_hash] = obj

    kept = list(by_hash.values())
    removed_dedup = len(candidates) - len(kept)

    _write_jsonl(MESSAGES_FILE, kept)

    kept_ids = [o.get("message_id") for o in kept if o.get("message_id")]
    kept_hashes = [o.get("ad_hash") for o in kept if o.get("ad_hash")]
    sync_engine_state(kept_ids)
    sync_engine_state_hashes(kept_hashes)

    print(
        f"[CLEANER] messages.jsonl: "
        f"{removed_age} removidas (3 meses), "
        f"{removed_buyer_age} compradores antigos removidos, "
        f"{removed_dedup} duplicatas removidas, "
        f"{len(kept)} mantidas."
    )


def clean_and_dedup_opportunities():
    """
    1. Remove oportunidades mais antigas que FIFTEEN_DAYS.
    2. Remove duplicatas por id (MD5 do par buyer+seller message_id).
       Quando há duplicata, mantém a mais recente (maior timestamp).
    """
    if not os.path.exists(OPPORTUNITIES_FILE):
        return

    now = int(time.time())
    cutoff = now - FIFTEEN_DAYS

    rows = _load_jsonl(OPPORTUNITIES_FILE)

    removed_age = 0
    candidates = []

    for raw, obj in rows:
        if obj is None:
            continue
        if obj.get("timestamp", 0) < cutoff:
            removed_age += 1
            continue
        candidates.append(obj)

    by_id: dict[str, dict] = {}
    for obj in candidates:
        oid = obj.get("id")
        if not oid:
            by_id[str(id(obj))] = obj
            continue
        existing = by_id.get(oid)
        if existing is None or obj.get("timestamp", 0) > existing.get("timestamp", 0):
            by_id[oid] = obj

    kept = list(by_id.values())
    removed_dedup = len(candidates) - len(kept)

    _write_jsonl(OPPORTUNITIES_FILE, kept)

    kept_ids = [o.get("id") for o in kept if o.get("id")]
    sync_dispatch_state(kept_ids)

    print(
        f"[CLEANER] opportunities.jsonl: "
        f"{removed_age} removidas (15 dias), "
        f"{removed_dedup} duplicatas removidas, "
        f"{len(kept)} mantidas."
    )


def reconcile_engine_state():
    """
    Reconstrói seen_ids e seen_hashes do zero a partir do messages.jsonl atual.
    Garante que o engine_state.json fique estritamente proporcional ao que
    existe no arquivo de mensagens — nunca maior.
    Cobre também o caso de messages.jsonl ausente ou corrompido.
    """
    if not os.path.exists(ENGINE_STATE_FILE):
        return

    if not os.path.exists(MESSAGES_FILE):
        with open(ENGINE_STATE_FILE, "w") as f:
            json.dump({"seen_ids": [], "seen_hashes": []}, f)
        print("[CLEANER] engine_state.json: zerado (messages.jsonl ausente).")
        return

    rows = _load_jsonl(MESSAGES_FILE)
    real_ids = [
        obj.get("message_id") for _, obj in rows if obj and obj.get("message_id")
    ]
    real_hashes = [obj.get("ad_hash") for _, obj in rows if obj and obj.get("ad_hash")]

    try:
        with open(ENGINE_STATE_FILE) as f:
            state = json.load(f)
    except Exception:
        print("[CLEANER] engine_state.json: não foi possível ler, pulando.")
        return

    previous_ids = len(state.get("seen_ids", []))
    previous_hashes = len(state.get("seen_hashes", []))

    state["seen_ids"] = real_ids
    state["seen_hashes"] = real_hashes

    with open(ENGINE_STATE_FILE, "w") as f:
        json.dump(state, f)

    print(
        f"[CLEANER] engine_state.json: reconciliado — "
        f"{previous_ids - len(real_ids)} IDs removidos, "
        f"{previous_hashes - len(real_hashes)} hashes removidos, "
        f"{len(real_ids)} IDs e {len(real_hashes)} hashes mantidos."
    )


def dedup_dispatch_state():
    """
    Remove entradas duplicadas no state.json (chaves 'sent').
    Como 'sent' é um dict {opp_id: valor}, duplicatas de chave são impossíveis
    por natureza do JSON — mas verificamos integridade e removemos valores None/inválidos.
    """
    if not os.path.exists(DISPATCH_STATE_FILE):
        return

    try:
        with open(DISPATCH_STATE_FILE) as f:
            state = json.load(f)
    except Exception:
        print("[CLEANER] state.json: não foi possível ler, pulando.")
        return

    sent = state.get("sent", {})
    cleaned = {k: v for k, v in sent.items() if k and v is not None}
    removed = len(sent) - len(cleaned)

    state["sent"] = cleaned

    with open(DISPATCH_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    print(f"[CLEANER] state.json: {removed} entradas inválidas/nulas removidas.")


if __name__ == "__main__":
    print(f"[CLEANER] Iniciando - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    clean_and_dedup_messages()
    clean_and_dedup_opportunities()
    reconcile_engine_state()
    dedup_dispatch_state()
    print("=" * 60)
    print("[CLEANER] Concluído.")
