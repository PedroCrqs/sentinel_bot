import json
import os
from pathlib import Path
import psycopg2
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Configuração do Banco
DB_NAME = os.getenv("DB_NAME", "sentinel_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

BASE_DIR = Path(__file__).resolve().parent.parent
JSONL_PATH = BASE_DIR / "data" / "messages.jsonl"

def migrate():
    if not JSONL_PATH.exists():
        print(f"[ERRO] Arquivo não encontrado em: {JSONL_PATH}")
        return

    print("Conectando ao PostgreSQL...")
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    cursor = conn.cursor()

    # Query de inserção. O 'ON CONFLICT DO NOTHING' evita que a mesma mensagem seja duplicada
    # caso rode o script duas vezes sem querer.
    query = """
        INSERT INTO raw_messages 
        (message_id, group_id, group_name, author_id, author_name, author_phone, message, ad_hash, timestamp, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING')
        ON CONFLICT (message_id) DO NOTHING;
    """

    count = 0
    print("Iniciando leitura do arquivo messages.jsonl...")
    
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
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
                count += 1
            except Exception as e:
                print(f"Erro ao processar linha: {e}")

    # Salva no banco de forma atômica
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"==================================================")
    print(f"🚀 Migração Concluída! {count} mensagens injetadas na fila.")
    print(f"==================================================")

if __name__ == "__main__":
    migrate()