import sys
from database import get_db_connection, release_db_connection
from graphs.neo4j_client import GraphClient

def purge_user(blocked_id: str):
    print(f"[PURGE] Iniciando expurgo total do usuário: {blocked_id}")
    
    # 1. PostgreSQL: remove oportunidades vinculadas primeiro para respeitar integridade
    conn = None
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM opportunities 
                    WHERE buyer_message_id IN (SELECT message_id FROM raw_messages WHERE author_id = %s OR author_phone = %s)
                       OR seller_message_id IN (SELECT message_id FROM raw_messages WHERE author_id = %s OR author_phone = %s)
                """, (blocked_id, blocked_id, blocked_id, blocked_id))
                deleted_opps = cursor.rowcount

                cursor.execute(
                    "DELETE FROM raw_messages WHERE author_id = %s OR author_phone = %s", 
                    (blocked_id, blocked_id)
                )
                deleted_rows = cursor.rowcount
            conn.commit()
        print(f"[PURGE] PostgreSQL: {deleted_rows} mensagens e {deleted_opps} oportunidades de {blocked_id} apagadas.")
    except Exception as e:
        print(f"[PURGE] Erro no PostgreSQL: {e}")
    finally:
        if conn:
            release_db_connection(conn)

    # 2. Neo4j: remove Pessoa e todas as entidades associadas (ofertas, demandas, mensagens)
    try:
        graph = GraphClient()
        query = """
        MATCH (p:Pessoa) 
        WHERE p.person_id = $blocked_id OR p.telefone = $blocked_id OR p.nome = $blocked_id
        OPTIONAL MATCH (p)-[:CRIOU|PUBLICOU|ENVIOU]->(x)
        DETACH DELETE x, p
        """
        with graph.driver.session() as session:
            session.run(query, blocked_id=blocked_id)
        graph.close()
        print(f"[PURGE] Neo4j: Usuário {blocked_id} e suas entidades (ofertas, demandas, mensagens) foram expurgados.")
    except Exception as e:
        print(f"[PURGE] Erro no Neo4j: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        purge_user(sys.argv[1])
    else:
        print("Uso: python purge_user.py <blocked_id>")
