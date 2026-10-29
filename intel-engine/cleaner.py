import time
from graphs.neo4j_client import GraphClient
from database import get_db_connection 

def purge_old_data_neo4j(limite_30d: int, limite_90d: int):
    """
    Remove nós de Mensagem antigos e limpa nós órfãos de Pessoas e Imóveis.
    Regra de Negócio: Ofertas duram 90 dias, Buscas duram 30 dias.
    """
    try:
        graph = GraphClient()
        query = """
        // 1. Apaga mensagens de OFERTA mais velhas que 90 dias
        MATCH (m:Mensagem)-[:ORIGINA]->(:Oferta) WHERE m.timestamp < $limite_90d
        DETACH DELETE m
        
        WITH 1 AS dummy
        
        // 2. Apaga mensagens de demanda mais velhas que 30 dias
        MATCH (m:Mensagem)-[:EXPRESSA]->(:Demanda) WHERE m.timestamp < $limite_30d
        DETACH DELETE m
        
        WITH 1 AS dummy
        
        // 3. Apaga Imóveis que não estão ligados a nenhuma Mensagem (órfãos)
        MATCH (i:Imovel) WHERE NOT ()-->(i)
        DETACH DELETE i
        
        WITH 1 AS dummy
        
        // 4. Apaga Pessoas que não enviaram nenhuma Mensagem ativa
        MATCH (p:Pessoa) WHERE NOT (p)-[:ENVIOU]->()
        DETACH DELETE p
        """
        with graph.driver.session() as session:
            session.run(query, limite_30d=limite_30d, limite_90d=limite_90d)
        graph.close()
        print(f"[CLEANER] Neo4j: Dados expirados expurgados (Ofertas > 90d, Buscas > 30d).")
    except Exception as e:
        print(f"[CLEANER] Erro ao limpar Neo4j: {e}")

def purge_old_data_sql(limite_timestamp: int):
    """
    Remove registros brutos antigos do PostgreSQL para otimizar armazenamento.
    """
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM raw_messages WHERE timestamp < %s", (limite_timestamp,))
                deleted_msgs = cursor.rowcount
                
                # Aproveita para limpar oportunidades órfãs muito velhas da tabela (cascade cuida da maioria, mas garante limpeza final)
                cursor.execute("DELETE FROM opportunities WHERE created_at < to_timestamp(%s)", (limite_timestamp,))
                deleted_opps = cursor.rowcount
            conn.commit()
        print(f"[CLEANER] PostgreSQL: {deleted_msgs} msgs e {deleted_opps} oportunidades antigas expurgadas.")
    except Exception as e:
        print(f"[CLEANER] Erro ao limpar PostgreSQL: {e}")

if __name__ == "__main__":
    print(f"[CLEANER] Iniciando Faxina de Bancos - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    limite_30d = int(time.time()) - (30 * 24 * 60 * 60)
    limite_90d = int(time.time()) - (90 * 24 * 60 * 60)
    
    # Executa a limpeza manual seguindo as mesmas regras do motor
    purge_old_data_sql(limite_90d)
    purge_old_data_neo4j(limite_30d, limite_90d)
    
    print("[CLEANER] Concluído.")
