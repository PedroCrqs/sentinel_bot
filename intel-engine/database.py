import hashlib
import json
import os
import psycopg2
import time
from psycopg2.pool import SimpleConnectionPool

from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Configuração de Conexão via Variáveis de Ambiente (ajustado para o .env)
DB_NAME = os.getenv("POSTGRES_DB", "imoveis")
DB_USER = os.getenv("POSTGRES_USER", "imoveis_app")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# Inicialização do Pool de Conexões (min=1, max=10 conexões por exemplo)
db_pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT
)

def get_db_connection():
    """Obtém uma conexão limpa a partir do pool."""
    return db_pool.getconn()

def release_db_connection(conn):
    """Devolve a conexão para o pool."""
    if conn:
        db_pool.putconn(conn)


# ==============================================================================
# BLOCO 1: GESTÃO DO INVENTÁRIO PRÓPRIO
# ==============================================================================

def get_available_properties() -> list[dict]:
    """Busca imóveis com status 'Disponível' direto do PostgreSQL."""
    query = "SELECT * FROM Imoveis WHERE ImovelStatus = 'Disponível';"
    conn = None
    
    try:
        conn = get_db_connection()
        with conn:
            # RealDictCursor faz o psycopg2 retornar dicionários Python nativos
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao buscar imóveis disponíveis: {e}")
        return []
    finally:
        release_db_connection(conn)


def get_property_details() -> list[dict]:
    """
    Retorna os imóveis próprios estruturados diretamente para a ingestão do Neo4j,
    ignorando completamente a necessidade de passar pelo normalizer (spaCy).
    """
    properties_available = get_available_properties()
    properties_details = []
    
    for prop in properties_available:
        description = prop.get("descricao")
        if not description:
            continue
            
        imovel_id = prop.get("imovelid")
        
        # Cria a estrutura exata que o `ingest_ad` do neo4j_client.py espera
        properties_details.append({
            "original_content": {
                "author_name": "Majesto (Imóvel Próprio)",
                "author_phone": None,
                "message_id": f"self-{imovel_id}",
                "timestamp": int(time.time()),
                "imovel_id": imovel_id
            },
            "intent": "oferece",
            "raw_text": description,
            # Adapte as chaves (bairro, tipo, etc.) para corresponderem às colunas reais do seu DB
            "neighborhood": [prop.get("bairro", "Desconhecido")], 
            "property_type": prop.get("tipo"),
            "price": prop.get("valorvenda") or prop.get("preco"),
            "bedrooms": prop.get("quartos"),
            "area_m2": prop.get("area"),
            "parking_spots": prop.get("vagas"),
            "seafront": prop.get("frente_mar", False)
        })

    return properties_details


# ==============================================================================
# BLOCO 2: FLUXO E FILA DO SENTINEL BOT (O que substitui o JSONL)
# ==============================================================================

def get_pending_messages() -> list[dict]:
    """Busca todas as mensagens enviadas pelo WhatsApp que ainda estão pendentes."""
    query = "SELECT * FROM raw_messages WHERE status = 'PENDING' ORDER BY timestamp ASC LIMIT 50;"
    conn = None
    
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao buscar mensagens pendentes: {e}")
        return []
    finally:
        release_db_connection(conn)


def update_message_status(message_id: str, status: str, normalized_data: dict | None = None):
    """
    Atualiza o status da mensagem e salva o JSON extraído pelo normalizer.
    Substitui o antigo engine_state.json.
    """
    from datetime import datetime, date

    query = """
        UPDATE raw_messages 
        SET status = %s, normalized_data = %s 
        WHERE message_id = %s;
    """
    
    def json_serial(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Tipo {type(obj)} não é serializável")

    conn = None
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                # O parâmetro default=json_serial entra em ação
                json_data = json.dumps(normalized_data, default=json_serial) if normalized_data else None
                cursor.execute(query, (status, json_data, message_id))
            conn.commit()
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao atualizar status da mensagem {message_id}: {e}")
    finally:
        release_db_connection(conn)


def save_opportunities(opportunities_list: list[dict]):
    """
    Salva os matches gerados pelo Neo4j na tabela transacional.
    Lê o formato simplificado e direto gerado pelo Cypher.
    """
    query = """
        INSERT INTO opportunities
            (buyer_message_id, seller_message_id, matched_imovel_id,
             match_score, match_details, dispatch_status)
        VALUES (%s, %s, %s, %s, %s, 'PENDING')
        ON CONFLICT (buyer_message_id, seller_message_id) DO NOTHING;
    """

    conn = None
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                for opp in opportunities_list:
                    # Garantir que a query Cypher no neo4j_client.py retorne estes IDs no dict!
                    buyer_msg_id = opp.get("buyer_message_id")
                    seller_msg_id = opp.get("seller_message_id")
                    matched_imovel_id = opp.get("matched_imovel_id") 
                    match_score = opp.get("score", 0)
                    match_details = json.dumps(opp)

                    cursor.execute(query, (
                        buyer_msg_id,
                        seller_msg_id,
                        matched_imovel_id,
                        match_score,
                        match_details,
                    ))
            conn.commit()
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao salvar lote de oportunidades: {e}")
    finally:
        release_db_connection(conn)
        