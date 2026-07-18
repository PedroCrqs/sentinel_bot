import os
from dotenv import load_dotenv, find_dotenv
from neo4j import GraphDatabase

load_dotenv(find_dotenv())

URI = os.getenv("NEO4J_URI", "")
USER = os.getenv("NEO4J_USERNAME", "")
PASSWORD = os.getenv("NEO4J_PASSWORD", "")

AUTH = (USER, PASSWORD)

class GraphClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(URI, auth=AUTH)

    def close(self):
        """Fecha a conexão com o banco de dados."""
        self.driver.close()

    def test_connection(self):
        """Testa se o Python consegue falar com o Neo4j."""
        try:
            self.driver.verify_connectivity()
            print("✅ Conectado ao Neo4j com sucesso!")
        except Exception as e:
            print(f"❌ Erro ao conectar: {e}")

    def ingest_ad(self, ad_data: dict):
        """
        Recebe o dicionário gerado pelo normalizer.py e insere no formato de Grafo.
        """
        original = ad_data.get("original_content", {})
        
        # Pega o primeiro bairro da lista, ou define como Desconhecido
        bairros = ad_data.get("neighborhood", [])
        bairro_principal = bairros[0] if bairros else "Desconhecido"

        # A query Cypher que desenha os nós e arestas
        query = """
        // Pessoa e Bairro (MERGE = Cria se não existir, usa se já existir)
        MERGE (p:Pessoa {telefone: $telefone})
        ON CREATE SET p.nome = $nome
        
        MERGE (b:Bairro {nome: $bairro})
        
        // Mensagem: Usa MERGE com id para evitar duplicatas
        MERGE (m:Mensagem {id: $msg_id})
        SET m.texto = $texto, m.timestamp = $ts
        MERGE (p)-[:ENVIOU]->(m)
        
        // Imóvel: Associa um ID derivado da mensagem para evitar nós soltos e duplicados
        MERGE (i:Imovel {id: $msg_id + '_imovel'})
        SET i.tipo = $tipo, 
            i.preco = $preco, 
            i.quartos = $quartos, 
            i.area = $area,
            i.vagas = $vagas,
            i.frente_mar = $frente_mar
            
        MERGE (i)-[:LOCALIZADO_EM]->(b)
        """

        # ================= DEBUG =================
        # print(f"CHAVES DISPONÍVEIS: {list(ad_data.keys())}")
        # print(f"VALOR DA INTENÇÃO: {ad_data.get('intent')}")
        # =========================================

        # Define se a pessoa está buscando ou oferecendo o imóvel
        intent = str(ad_data.get("intent", "")).lower()
        
        if intent in ["buy", "buying", "compra", "comprar", "busca", "buscando", "interesse", "demand", "procura", "procurando", "demanda"]:
            query += "\nMERGE (m)-[:BUSCA]->(i)"
        else:
            query += "\nMERGE (m)-[:OFERECE]->(i)"

        # Executa a query injetando os valores do dicionário
        with self.driver.session() as session:
            session.run(query, 
                telefone=original.get("author_phone", "Desconhecido"),
                nome=original.get("author_name", "Desconhecido"),
                msg_id=original.get("message_id", "Desconhecido"),
                texto=ad_data.get("raw_text", ""),
                ts=original.get("timestamp", 0),
                tipo=ad_data.get("property_type"),
                preco=ad_data.get("price"),
                quartos=ad_data.get("bedrooms"),
                area=ad_data.get("area_m2"),
                vagas=ad_data.get("parking_spots"),
                frente_mar=ad_data.get("seafront", False),
                bairro=bairro_principal
            )


if __name__ == "__main__":
    cliente = GraphClient()
    cliente.test_connection()
    cliente.close()