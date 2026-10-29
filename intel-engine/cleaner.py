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
      - Ofertas de terceiros com mais de 90 dias são expurgadas (junto com a mensagem de origem).
      - Demandas de compradores com mais de 15 dias são expurgadas (junto com a mensagem de expressão).
      - Imóveis próprios do inventário Majesto NUNCA são expurgados por tempo (são controlados pelo sync).
      - Nós órfãos de Imóveis (sem nenhuma oferta associada) e Pessoas (sem ofertas ou demandas ativas) são removidos.
    """
    try:
        graph = GraphClient()
        with graph.driver.session() as session:
            # 1. Apaga ofertas de terceiros (> 90 dias) e mensagens que as originaram
            # Protege ofertas de inventário próprio Majesto ('self-offer:*')
            q1 = """
            MATCH (m:Mensagem)-[:ORIGINA]->(o:Oferta)
            WHERE m.timestamp < $limite_90d AND NOT o.offer_id STARTS WITH 'self-offer:'
            DETACH DELETE m, o
            """
            session.run(q1, limite_90d=limite_90d)

            # 2. Apaga demandas de compradores (> 15 dias) e mensagens associadas
            q2 = """
            MATCH (m:Mensagem)-[:EXPRESSA]->(d:Demanda)
            WHERE m.timestamp < $limite_15d
            DETACH DELETE m, d
            """
            session.run(q2, limite_15d=limite_15d)

            # 3. Apaga Imóveis de terceiros que não possuem nenhuma Oferta ativa
            # Protege imóveis cadastrados do inventário Majesto (prefixo 'imovel_')
            q3 = """
            MATCH (i:Imovel)
            WHERE NOT ()-[:REFERE_SE_A]->(i) AND NOT i.id STARTS WITH 'imovel_'
            DETACH DELETE i
            """
            session.run(q3)

            # 4. Apaga Pessoas órfãs (que não criaram Demanda nem publicaram Oferta ativa)
            # Protege a entidade de sistema 'system:majesto'
            q4 = """
            MATCH (p:Pessoa)
            WHERE NOT (p)-[:CRIOU]->() AND NOT (p)-[:PUBLICOU]->() AND p.person_id <> 'system:majesto'
            DETACH DELETE p
            """
            session.run(q4)

        graph.close()
        print(f"[CLEANER] Neo4j: Expurgo concluído (Ofertas > 90d, Compradores > 15d, nós órfãos limpos).")
    except Exception as e:
        print(f"[CLEANER] Erro ao limpar Neo4j: {e}")


def purge_old_data_sql(limite_15d: int, limite_90d: int):
    """
    Remove do PostgreSQL oportunidades antigas e mensagens expiradas para otimizar armazenamento.
    Executa a deleção de opportunities antes de raw_messages para respeitar integridade referencial.
    """
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                # Remove oportunidades criadas há mais de 15 dias primeiro
                cursor.execute("DELETE FROM opportunities WHERE created_at < to_timestamp(%s)", (limite_15d,))
                deleted_opps = cursor.rowcount

                # Remove mensagens de terceiros mais antigas que 90 dias
                cursor.execute("DELETE FROM raw_messages WHERE timestamp < %s", (limite_90d,))
                deleted_msgs = cursor.rowcount
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
