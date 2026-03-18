import json

MESSAGES_FILE = "../data/messages.jsonl"
OPPORTUNITIES_FILE = "../data/opportunities.jsonl"
# Add id from user who you want to purge
BLOCKED_ID = "37658826899485@lid"


def purge_messages():
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"[PURGE] {MESSAGES_FILE} não encontrado, pulando.")
        return

    kept, removed = [], 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if msg.get("author_id") == BLOCKED_ID:
                removed += 1
            else:
                kept.append(line)
        except json.JSONDecodeError:
            kept.append(line)

    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))

    print(f"[PURGE] messages.jsonl: {removed} removidas, {len(kept)} mantidas.")


def purge_opportunities():
    try:
        with open(OPPORTUNITIES_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"[PURGE] {OPPORTUNITIES_FILE} não encontrado, pulando.")
        return

    kept, removed = [], 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            opp = json.loads(line)
            buyer_id = opp.get("buyer", {}).get("original_content", {}).get("author_id")
            seller_id = (
                opp.get("seller", {}).get("original_content", {}).get("author_id")
            )
            if BLOCKED_ID in (buyer_id, seller_id):
                removed += 1
            else:
                kept.append(line)
        except json.JSONDecodeError:
            kept.append(line)

    with open(OPPORTUNITIES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))

    print(f"[PURGE] opportunities.jsonl: {removed} removidas, {len(kept)} mantidas.")


if __name__ == "__main__":
    purge_messages()
    purge_opportunities()
    print("[PURGE] Concluído.")
