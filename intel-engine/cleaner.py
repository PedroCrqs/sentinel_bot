import time
from graphs.neo4j_client import GraphClient
from database import get_db_connection

# ==============================================================================
# REGRAS DE RETENÇÃO E FAXINA (v2.0.0)
# - Ofertas de imóveis duram no máximo 90 dias
# - Demandas de compradores duram no máximo 15 dias
# ==============================================================================
RETENTION_OFFERS_SECONDS = 90 * 24 * 60 * 60  # 90 dias
RETENTION_BUYERS_SECONDS = 15 * 24 * 60 * 60  # 15 dias


def purge_old_data_neo4j(limite_15d: int, limite_90d: int):
    """
    Remove mensagens e nós expirados do grafo Neo4j e limpa nós órfãos.
    Regra de Negócio:
      - Ofertas de terceiros com mais de 90 dias são expurgadas.
      - Demandas de compradores com mais de 15 dias são expurgadas.
      - Imóveis próprios do inventário Majesto NUNCA são expurgados por tempo (são controlados pelo sync).
    """
    try:
        graph = GraphClient()
        query = """
        // 1. Apaga mensagens e nós de OFERTA de terceiros mais velhas que 90 dias
        MATCH (m:Mensagem)-[:ORIGINA]->(o:Oferta)
        WHERE m.timestamp < $limite_90d
        DETACH DELETE m, o

        WITH 1 AS dummy

        // 2. Apaga mensagens e nós de DEMANDA (compradores) mais velhas que 15 dias
        MATCH (m:Mensagem)-[:EXPRESSA]->(d:Demanda)
        WHERE m.timestamp < $limite_15d
        DETACH DELETE m, d

        WITH 1 AS dummy

        // 3. Apaga Imóveis que não estão ligados a nenhuma Oferta ativa (órfãos de terceiros)
        MATCH (i:Imovel)
        WHERE NOT ()-[:REFERE_SE_A]->(i) AND NOT ()-[:LOCALIZADO_EM]->(i) AND NOT (i)-[:LOCALIZADO_EM]->()
        DETACH DELETE i

        WITH 1 AS dummy

        // 4. Apaga Pessoas que não criaram Demanda nem publicaram Oferta ativa
        MATCH (p:Pessoa)
        WHERE NOT (p)-[:CRIOU]->() AND NOT (p)-[:PUBLICOU]->() AND p.person_id <> 'system:majesto'
        DETACH DELETE p
        """
        with graph.driver.session() as session:
            session.run(query, limite_15d=limite_15d, limite_90d=limite_90d)
        graph.close()
        print(f"[CLEANER] Neo4j: Expurgo concluído (Ofertas > 90d, Compradores > 15d, nós órfãos limpos).")
    except Exception as e:
        print(f"[CLEANER] Erro ao limpar Neo4j: {e}")


def purge_old_data_sql(limite_15d: int, limite_90d: int):
    """
    Remove do PostgreSQL mensagens expiradas e oportunidades antigas para otimizar armazenamento.
    """
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                # Remove mensagens de terceiros mais antigas que 90 dias
                cursor.execute("DELETE FROM raw_messages WHERE timestamp < %s", (limite_90d,))
                deleted_msgs = cursor.rowcount

                # Remove oportunidades criadas há mais de 15 dias
                cursor.execute("DELETE FROM opportunities WHERE created_at < to_timestamp(%s)", (limite_15d,))
                deleted_opps = cursor.rowcount
            conn.commit()
        print(f"[CLEANER] PostgreSQL: {deleted_msgs} mensagens antigas (>90d) e {deleted_opps} oportunidades (>15d) expurgadas.")
    except Exception as e:
        print(f"[CLEANER] Erro ao limpar PostgreSQL: {e}")


def run_cleaner():
    now = int(time.time())
    limite_15d = now - RETENTION_BUYERS_SECONDS
    limite_90d = now - RETENTION_OFFERS_SECONDS
    print(f"[CLEANER] Iniciando faxina programada - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    purge_old_data_sql(limite_15d, limite_90d)
    purge_old_data_neo4j(limite_15d, limite_90d)
    print("[CLEANER] Concluído com sucesso.")


if __name__ == "__main__":
    run_cleaner()
