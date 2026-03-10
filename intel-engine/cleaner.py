import json
import time
import os
from classifier import classify_message

MESSAGES_FILE = "../data/messages.jsonl"
OPPORTUNITIES_FILE = "../data/opportunities.jsonl"

THREE_MONTHS = 7_776_000
THIRTY_DAYS = 2_592_000


def clean_old_messages():
    if not os.path.exists(MESSAGES_FILE):
        return

    now = int(time.time())
    cutoff = now - THREE_MONTHS

    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    kept = []
    removed = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if msg.get("timestamp", 0) >= cutoff:
                kept.append(line)
            else:
                removed += 1
        except json.JSONDecodeError:
            kept.append(line)

    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))

    print(f"[CLEANER] messages.jsonl: {removed} removidas, {len(kept)} mantidas.")


def clean_old_opportunities():
    if not os.path.exists(OPPORTUNITIES_FILE):
        return

    now = int(time.time())
    cutoff = now - THIRTY_DAYS

    with open(OPPORTUNITIES_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    kept = []
    removed = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            opp = json.loads(line)
            if opp.get("timestamp", 0) >= cutoff:
                kept.append(line)
            else:
                removed += 1
        except json.JSONDecodeError:
            kept.append(line)

    with open(OPPORTUNITIES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))

    print(f"[CLEANER] opportunities.jsonl: {removed} removidas, {len(kept)} mantidas.")


def clean_old_buyers():
    if not os.path.exists(MESSAGES_FILE):
        return

    now = int(time.time())
    cutoff = now - THIRTY_DAYS

    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    kept = []
    removed = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            classification = classify_message(msg)
            if classification == "buying" and msg.get("timestamp", 0) < cutoff:
                removed += 1
            else:
                kept.append(line)
        except json.JSONDecodeError:
            kept.append(line)

    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))

    print(f"[CLEANER] buyers antigos: {removed} removidos, {len(kept)} mantidas.")


if __name__ == "__main__":
    print(f"[CLEANER] Iniciando - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    clean_old_messages()
    clean_old_opportunities()
    clean_old_buyers()
    print("=" * 60)
    print("[CLEANER] Concluído.")