import sys
from database import get_db_connection
from graphs.neo4j_client import GraphClient

BLOCKED_ID = "228707713171512@lid"

def purge_user(blocked_id: str):
    print(f"[PURGE] Iniciando expurgo total do usuário: {blocked_id}")
    
    # 1. PostgreSQL
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                # O ON DELETE CASCADE cuidará de deletar as oportunidades ligadas a essas mensagens
                cursor.execute(
                    "DELETE FROM raw_messages WHERE author_id = %s OR author_phone = %s", 
                    (blocked_id, blocked_id)
                )
                deleted_rows = cursor.rowcount
            conn.commit()
        print(f"[PURGE] PostgreSQL: {deleted_rows} mensagens de {blocked_id} apagadas (matches em cascata deletados).")
    except Exception as e:
        print(f"[PURGE] Erro no PostgreSQL: {e}")

    # 2. Neo4j
    try:
        graph = GraphClient()
        query = """
        MATCH (p:Pessoa) WHERE p.telefone = $blocked_id OR p.nome = $blocked_id OR p.pessoa_id = $blocked_id
        OPTIONAL MATCH (p)-[:ENVIOU]->(m:Mensagem)
        DETACH DELETE m, p
        """
        with graph.driver.session() as session:
            session.run(query, blocked_id=blocked_id)
        graph.close()
        print(f"[PURGE] Neo4j: Usuário {blocked_id} e suas mensagens/arestas foram expurgados.")
    except Exception as e:
        print(f"[PURGE] Erro no Neo4j: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        purge_user(sys.argv[1])
    else:
        purge_user(BLOCKED_ID)
    print("[PURGE] Concluído.")
