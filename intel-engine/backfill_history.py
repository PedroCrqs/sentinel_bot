"""
Script de Backfill Histórico e Carga Inicial do Grafo Neo4j.

Regras de Retenção Aplicadas:
  - Ofertas de terceiros: apenas dos últimos 90 dias
  - Demandas de compradores: apenas dos últimos 15 dias
  - Deduplicação estrita por ad_hash (anúncios repetidos são descartados)
  - Imóveis próprios: mantidos via inventory_sync
"""

import time
import logging
from classifier import run_classifier
from normalizer import run_normalizer
from graphs.neo4j_client import GraphClient
from database import get_db_connection, release_db_connection, update_message_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("backfill")

NOW = int(time.time())
LIMIT_BUYERS_15D = NOW - (15 * 24 * 60 * 60)
LIMIT_OFFERS_90D = NOW - (90 * 24 * 60 * 60)


def load_candidate_messages() -> list[dict]:
    """Busca do PostgreSQL mensagens elegíveis pelas regras de tempo e deduplicação."""
    # Busca mensagens dos últimos 90 dias
    query = """
        SELECT message_id, group_id, group_name, author_id, author_name,
               author_phone, message, ad_hash, timestamp, status
        FROM raw_messages
        WHERE timestamp >= %s
        ORDER BY timestamp ASC;
    """
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, (LIMIT_OFFERS_90D,))
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        LOGGER.info("Carregadas %d mensagens dos últimos 90 dias do PostgreSQL.", len(rows))
        return rows
    finally:
        release_db_connection(conn)


def run_backfill():
    raw_rows = load_candidate_messages()
    if not raw_rows:
        LOGGER.info("Nenhuma mensagem elegível encontrada no banco.")
        return

    # 1. Deduplicação por ad_hash em memória (mantém o mais recente)
    seen_hashes = {}
    for r in raw_rows:
        h = r.get("ad_hash")
        if h:
            seen_hashes[h] = r
        else:
            mid = r.get("message_id")
            seen_hashes[mid] = r

    unique_messages = list(seen_hashes.values())
    LOGGER.info("Deduplicação por ad_hash: %d mensagens únicas selecionadas.", len(unique_messages))

    # 2. Classificação em Lote (NLP)
    LOGGER.info("Iniciando classificação NLP (spaCy pt_core_news_lg)...")
    sellers, buyers, useless = run_classifier(unique_messages)
    LOGGER.info("Classificação: %d Vendedores | %d Compradores | %d Inúteis", len(sellers), len(buyers), len(useless))

    # 3. Filtro de idade estrito para Compradores (máximo 15 dias)
    active_buyers = [
        b for b in buyers
        if (b.data.get("timestamp") or 0) >= LIMIT_BUYERS_15D
    ]
    LOGGER.info("Compradores ativos (<= 15 dias): %d (descartados %d com > 15 dias)", len(active_buyers), len(buyers) - len(active_buyers))

    # 4. Normalização
    LOGGER.info("Iniciando normalização de atributos (bairros, tipologias, valores)...")
    sellers_pad, buyers_pad = run_normalizer(sellers, active_buyers)

    # 5. Ingestão em Grafo (Neo4j)
    LOGGER.info("Conectando ao Neo4j para ingestão em lote...")
    graph = GraphClient()
    try:
        ingested_sellers = 0
        for s in sellers_pad:
            try:
                graph.ingest_ad(s)
                ingested_sellers += 1
            except Exception as e:
                LOGGER.warning("Falha ao ingerir vendedor %s: %s", s.get("original_content", {}).get("message_id"), e)

        ingested_buyers = 0
        for b in buyers_pad:
            try:
                graph.ingest_ad(b)
                ingested_buyers += 1
            except Exception as e:
                LOGGER.warning("Falha ao ingerir comprador %s: %s", b.get("original_content", {}).get("message_id"), e)

        LOGGER.info("Ingestão concluída no Neo4j: %d Ofertas | %d Demandas.", ingested_sellers, ingested_buyers)

        # 6. Atualização de status no PostgreSQL
        LOGGER.info("Atualizando status das mensagens no PostgreSQL...")
        for s in sellers_pad:
            mid = s.get("original_content", {}).get("message_id")
            if mid:
                update_message_status(mid, "PROCESSED", normalized_data=s)
        for b in buyers_pad:
            mid = b.get("original_content", {}).get("message_id")
            if mid:
                update_message_status(mid, "PROCESSED", normalized_data=b)
        for u in useless:
            mid = u.data.get("message_id") if hasattr(u, "data") else u.get("message_id")
            if mid:
                update_message_status(mid, "PROCESSED")

        # 7. Avaliação de Oportunidades geradas (critério: preço obrigatório e score > 50)
        opps = graph.match_opportunities()
        LOGGER.info("🎉 TOTAL DE MATCHES IDENTIFICADOS NO GRAFO: %d", len(opps))
        for o in opps[:5]:
            LOGGER.info("  👉 [Score %s] Comprador: %s x Vendedor: %s (Bairros: %s)",
                        o.get("score"),
                        o.get("buyer", {}).get("name"),
                        o.get("seller", {}).get("name"),
                        o.get("matched_neighborhoods"))

    finally:
        graph.close()


if __name__ == "__main__":
    run_backfill()
