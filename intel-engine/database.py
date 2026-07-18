import hashlib
import os
import psycopg2

from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Configuração de Conexão via Variáveis de Ambiente
DB_NAME = os.getenv("DB_NAME", "sentinel_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

def get_db_connection():
    """Garante uma nova conexão limpa com o PostgreSQL."""
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )


# ==============================================================================
# BLOCO 1: GESTÃO DO INVENTÁRIO PRÓPRIO
# ==============================================================================

def get_available_properties() -> list[dict]:
    """Busca imóveis com status 'Disponível' direto do PostgreSQL."""
    query = "SELECT * FROM Imoveis WHERE ImovelStatus = 'Disponível';"
    
    try:
        with get_db_connection() as conn:
            # RealDictCursor faz o psycopg2 retornar dicionários Python nativos
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao buscar imóveis disponíveis: {e}")
        return []


def get_property_details() -> list[dict]:
    """
    Mantém a mesma inteligência do seu pipeline original:
    Retorna os imóveis próprios simulando a 'forma' de um message_data vindo do WhatsApp.
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
            }
        )
    return properties_details


# ==============================================================================
# BLOCO 2: FLUXO E FILA DO SENTINEL BOT (O que substitui o JSONL)
# ==============================================================================

def get_pending_messages() -> list[dict]:
    """Busca todas as mensagens enviadas pelo WhatsApp que ainda estão pendentes."""
    query = "SELECT * FROM raw_messages WHERE status = 'PENDING' ORDER BY timestamp ASC LIMIT 50;"
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao buscar mensagens pendentes: {e}")
        return []


def update_message_status(message_id: str, status: str, normalized_data: dict | None = None):
    """
    Atualiza o status da mensagem e salva o JSON extraído pelo normalizer.
    Substitui o antigo engine_state.json.
    """
    import json
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

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # O parâmetro default=json_serial entra em ação
                json_data = json.dumps(normalized_data, default=json_serial) if normalized_data else None
                cursor.execute(query, (status, json_data, message_id))
            conn.commit()
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao atualizar status da mensagem {message_id}: {e}")


def save_opportunities(opportunities_list: list[dict]):
    """
    Salva os matches gerados pelo matcher.py na tabela transacional.
    Substitui o antigo self_opportunities.jsonl.
    """
    query = """
        INSERT INTO opportunities (buyer_message_id, matched_imovel_id, match_score, dispatch_status)
        VALUES (%s, %s, %s, 'QUEUED');
    """
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                for opp in opportunities_list:
                    # Mapeia as chaves que seu matcher.py gera para as colunas do Postgres
                    cursor.execute(query, (
                        opp.get("buyer_message_id"),
                        opp.get("imovel_id"),
                        opp.get("score")
                    ))
            conn.commit()
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao salvar lote de oportunidades: {e}")