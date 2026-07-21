import json
import os
from pathlib import Path
import psycopg2
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Usa a mesma DATABASE_URL que o resto do projeto (main.js, database.py)
DATABASE_URL = os.environ["DATABASE_URL"]

BASE_DIR = Path(__file__).resolve().parent.parent
JSONL_PATH = BASE_DIR / "data" / "messages.jsonl"

def migrate():
    if not JSONL_PATH.exists():
        print(f"[ERRO] Arquivo não encontrado em: {JSONL_PATH}")
        return

    print("Conectando ao PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # Query de inserção. O 'ON CONFLICT DO NOTHING' evita que a mesma mensagem seja duplicada
    # caso rode o script duas vezes sem querer.
    query = """
        INSERT INTO raw_messages 
        (message_id, group_id, group_name, author_id, author_name, author_phone, message, ad_hash, timestamp, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING')
        ON CONFLICT (message_id) DO NOTHING;
    """

    inserted = 0
    skipped = 0
    errors = 0

    print("Iniciando leitura do arquivo messages.jsonl...")

    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue

            try:
                data = json.loads(line)
                cursor.execute(query, (
                    data.get("message_id"),
                    data.get("group_id"),
                    data.get("group_name"),
                    data.get("author_id"),
                    data.get("author_name"),
                    data.get("author_phone"),
                    data.get("message"),
                    data.get("ad_hash"),
                    data.get("timestamp")
                ))
                # rowcount = 1 se inseriu de fato, 0 se ON CONFLICT DO NOTHING pulou
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1

                # Commit por linha: garante que uma falha isolada não
                # deixa a transação "abortada" para as linhas seguintes.
                conn.commit()

            except Exception as e:
                errors += 1
                print(f"Erro na linha {line_number}: {e}")
                conn.rollback()  # limpa o estado da transação antes de seguir

    cursor.close()
    conn.close()

    print(f"==================================================")
    print(f"🚀 Migração concluída!")
    print(f"   Inseridas: {inserted}")
    print(f"   Já existentes (puladas): {skipped}")
    print(f"   Erros: {errors}")
    print(f"==================================================")

if __name__ == "__main__":
    migrate()
