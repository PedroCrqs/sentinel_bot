import json
import os
from pathlib import Path
import psycopg2
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

DB_NAME = os.getenv("DB_NAME", "sentinel_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

BASE_DIR = Path(__file__).resolve().parent.parent
OPP_FILE = BASE_DIR / "data" / "opportunities.jsonl"
SELF_OPP_FILE = BASE_DIR / "data" / "self_opportunities.jsonl"

def migrate_file(filepath, cursor, table_name="opportunities"):
    if not filepath.exists():
        print(f"⚠️ Arquivo não encontrado: {filepath.name} (Ignorando...)")
        return 0

    # Insere com status 'SENT' para o wpp-egress não disparar de novo
    query = f"""
        INSERT INTO {table_name} (buyer_message_id, seller_message_id, score, match_details, status)
        VALUES (%s, %s, %s, %s, 'SENT')
        ON CONFLICT DO NOTHING;
    """

    count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                opp = json.loads(line)
                
                # Extrai os IDs para preencher a tabela corretamente
                # O JSON antigo tem estruturas como opp['buyer']['id'] ou opp['buyer']['message_id']
                buyer_id = opp.get("buyer", {}).get("id") or opp.get("buyer", {}).get("message_id")
                seller_id = opp.get("seller", {}).get("id") or opp.get("seller", {}).get("message_id")
                score = opp.get("score", 0)
                
                # Converte o dicionário inteiro para texto JSON para salvar no banco
                match_details_json = json.dumps(opp)

                cursor.execute(query, (buyer_id, seller_id, score, match_details_json))
                count += 1
            except Exception as e:
                print(f"Erro ao migrar linha em {filepath.name}: {e}")
                
    return count

def migrate_all():
    print("Conectando ao PostgreSQL...")
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    cursor = conn.cursor()

    print("Migrando opportunities.jsonl...")
    count_opps = migrate_file(OPP_FILE, cursor)
    
    print("Migrando self_opportunities.jsonl...")
    count_self = migrate_file(SELF_OPP_FILE, cursor)

    conn.commit()
    cursor.close()
    conn.close()

    print(f"==================================================")
    print(f"🚀 Migração Concluída!")
    print(f"✅ {count_opps} oportunidades normais migradas.")
    print(f"✅ {count_self} oportunidades próprias migradas.")
    print(f"🔒 Todas marcadas como 'SENT' para evitar reenvio.")
    print(f"==================================================")

if __name__ == "__main__":
    migrate_all()