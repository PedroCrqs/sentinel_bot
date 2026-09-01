import hashlib
import json
import psycopg2
import time

from psycopg2.pool import SimpleConnectionPool

from psycopg2.extras import Json, RealDictCursor
from runtime_config import validated_database_settings
from inventory_adapter import map_inventory_row

# Inicialização do Pool de Conexões (min=1, max=10 conexões por exemplo)
db_pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    **validated_database_settings(),
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
    """Read the external inventory and return canonical Sentinel rows.

    ``public.imoveis`` is external/shared inventory. The explicit column list
    and LEFT JOIN keep its physical schema at this integration boundary.
    """
    query = """
        SELECT i.imovelid, i.tipologia, i.quartos, i.vagas, i.valor,
               i.metragem, i.sol, i.bairroid, i.imovelstatus,
               i.descricao, i.datacadastro, b.nome AS bairro_nome
        FROM public.imoveis AS i
        LEFT JOIN public.bairros AS b ON b.bairroid = i.bairroid
        WHERE i.imovelstatus = %s
    """
    conn = None
    
    try:
        conn = get_db_connection()
        with conn:
            # RealDictCursor faz o psycopg2 retornar dicionários Python nativos
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, ("Disponível",))
                rows = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao buscar imóveis disponíveis: {e}")
        return []
    finally:
        release_db_connection(conn)

    # Adapter errors are deliberately outside the database error handler:
    # malformed external inventory must be visible to the caller.
    return [map_inventory_row(row) for row in rows]


def get_inventory_snapshot() -> list[dict]:
    """Read all external inventory rows as canonical Sentinel properties.

    Database errors propagate because an incomplete snapshot must never mark
    existing properties as missing.
    """
    query = """
        SELECT i.imovelid, i.tipologia, i.quartos, i.vagas, i.valor,
               i.metragem, i.sol, i.bairroid, i.imovelstatus,
               i.descricao, i.datacadastro, b.nome AS bairro_nome
        FROM public.imoveis AS i
        LEFT JOIN public.bairros AS b ON b.bairroid = i.bairroid
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                rows = [dict(row) for row in cursor.fetchall()]
        return [map_inventory_row(row) for row in rows]
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
        description = prop.get("description")
        if not description:
            continue
            
        imovel_id = prop["property_id"]
        
        # Cria a estrutura exata que o `ingest_ad` do neo4j_client.py espera
        properties_details.append({
            "original_content": {
                "author_name": "Majesto (Imóvel Próprio)",
                "author_id": "system:majesto",
                "author_phone": None,
                "message_id": f"self-{imovel_id}",
                "timestamp": int(time.time()),
                "imovel_id": imovel_id,
                "source": "inventory",
            },
            "intent": "oferece",
            "raw_text": description,
            # Adapte as chaves (bairro, tipo, etc.) para corresponderem às colunas reais do seu DB
            "neighborhood": [prop["neighborhood"]],
            "property_type": prop["property_type"],
            "price": prop["price"],
            "bedrooms": prop["bedrooms"],
            "area_m2": prop["area"],
            "parking_spots": prop["parking_spots"],
            # The external schema has no frente_mar column: None means unknown.
            "seafront": None,
            "status": prop["status"],
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
        raise
    finally:
        release_db_connection(conn)


def save_opportunities(opportunities_list: list[dict]) -> list[int]:
    """Salva os matches gerados e retorna os IDs das novas oportunidades."""
    query = """
        INSERT INTO opportunities
            (demand_id, offer_id, buyer_message_id, seller_message_id,
             matched_imovel_id, match_score, match_details, rule_version,
             dispatch_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING')
        ON CONFLICT (buyer_message_id, seller_message_id) DO NOTHING
        RETURNING opportunity_id;
    """
    inserted_ids = []
    conn = None
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                for opp in opportunities_list:
                    demand_id = opp.get("demand_id")
                    offer_id = opp.get("offer_id")
                    buyer_msg_id = opp.get("buyer_message_id")
                    seller_msg_id = opp.get("seller_message_id")
                    matched_imovel_id = opp.get("matched_imovel_id") 
                    match_score = opp.get("score", 0)
                    rule_version = opp.get("rule_version", "v1")
                    match_details = Json(opp)

                    cursor.execute(query, (
                        demand_id, offer_id, buyer_msg_id, seller_msg_id,
                        matched_imovel_id, match_score, match_details,
                        rule_version,
                    ))
                    
                    # Pega o ID gerado pelo banco se a inserção ocorreu (ignora conflitos)
                    row = cursor.fetchone()
                    if row:
                        inserted_ids.append(row[0])
            conn.commit()
        return inserted_ids
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao salvar oportunidades: {e}")
        raise
    finally:
        release_db_connection(conn)


def get_message_by_id(message_id: str) -> dict | None:
    """Busca uma única mensagem no banco pelo ID enviado pelo RabbitMQ."""
    query = "SELECT * FROM raw_messages WHERE message_id = %s;"
    conn = None
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, (message_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        print(f"[ERRO BANCO] Falha ao buscar mensagem {message_id}: {e}")
        raise
    finally:
        release_db_connection(conn)
