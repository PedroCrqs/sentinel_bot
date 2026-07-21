import hashlib
import json
import os
import psycopg2
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
    Mantém a mesma inteligência do seu pipeline original:
    Retorna os imóveis próprios simulando a 'forma' de um message_data vindo do WhatsApp.

    IMPORTANTE: inclui imovel_id para que o matcher/normalizer consigam
    propagar o ImovelID real até a tabela opportunities.matched_imovel_id.
    """
    properties_available = get_available_properties()
    properties_details = []
    
    for prop in properties_available:
        description = prop.get("descricao")  # PostgreSQL adota chaves em lowercase por padrão
        if not description:
            continue
            
        properties_details.append(
            {
                "message_id": f"self-{hashlib.md5(description.encode()).hexdigest()}",
                "message": description,
                "author_name": "Majesto",
                "author_phone": None,
                "imovel_id": prop.get("imovelid"),  # preserva o ID real do imóvel
            }
        )
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
    Salva os matches gerados pelo matcher.py na tabela transacional.
    Substitui o antigo self_opportunities.jsonl.

    Cada item de opportunities_list tem o formato:
        {"buyer": {...}, "seller": {...}, "score": int}
    (retornado por matcher.get_opportunity)

    matched_imovel_id vem de seller["original_content"]["imovel_id"] --
    esse campo é propagado desde get_property_details() (database.py)
    através de run_self_normalizer() (normalizer.py), que guarda o dict
    original inteiro dentro de "original_content".
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
                    buyer_message_id = opp["buyer"]["original_content"]["message_id"]
                    seller_message_id = opp["seller"]["original_content"]["message_id"]
                    matched_imovel_id = opp["seller"]["original_content"].get("imovel_id")
                    match_score = opp["score"]
                    match_details = json.dumps(opp)

                    cursor.execute(query, (
                        buyer_message_id,
                        seller_message_id,
                        matched_imovel_id,
                        match_score,
                        match_details,
                    ))
            conn.commit()
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao salvar lote de oportunidades: {e}")
    finally:
        release_db_connection(conn)
