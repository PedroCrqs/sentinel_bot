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
            i.frente_mar = $frente_mar,
            i.condominio = $condominio,
            i.sol = $sol,
            i.perto_praia = $perto_praia
            
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
                condominio=ad_data.get("condominium", False),
                sol=ad_data.get("sun_type"),
                perto_praia=ad_data.get("nearbeach", False),
                bairro=bairro_principal
            )

    def match_opportunities(self):
        """
        Cruza intenções no grafo aplicando as regras estritas e o sistema 
        de pontuação do antigo matcher.py diretamente no banco de dados.
        """
        query = """
        MATCH (comprador:Pessoa)-[:ENVIOU]->(m_busca:Mensagem)-[:BUSCA]->(i_busca:Imovel)-[:LOCALIZADO_EM]->(b_busca:Bairro)
        MATCH (vendedor:Pessoa)-[:ENVIOU]->(m_oferece:Mensagem)-[:OFERECE]->(i_oferece:Imovel)-[:LOCALIZADO_EM]->(b_oferece:Bairro)
        
        // -------------------------------------------------------------
        // 1. REGRAS DE BLOQUEIO (Equivalente aos "continue" do Python)
        // -------------------------------------------------------------
        WHERE comprador.telefone <> vendedor.telefone
          
          // Bairro (Match exato ou comprador não especificou)
          AND (b_busca.nome = 'Desconhecido' OR b_busca.nome = b_oferece.nome)
          
          // Preço (Entre 80% do budget e Budget + 50k)
          AND (i_busca.preco IS NULL OR (i_oferece.preco >= (i_busca.preco * 0.80) AND i_oferece.preco <= (i_busca.preco + 50000)))
          
          // Quartos (Vendedor deve ter maior ou igual)
          AND (i_busca.quartos IS NULL OR i_oferece.quartos >= i_busca.quartos)
          
          // Se o comprador exige frente pro mar, o vendedor DEVE ter
          AND (i_busca.frente_mar = false OR i_oferece.frente_mar = true)

        // -------------------------------------------------------------
        // 2. SISTEMA DE SCORING (Equivalente ao OPPORTUNITY_SIGNALS)
        // -------------------------------------------------------------
        WITH comprador, m_busca, i_busca, b_busca, vendedor, m_oferece, i_oferece, b_oferece,
             
             // Pontos garantidos por ter passado nas regras de bloqueio acima
             (10 + 10 + 5) AS score_base, // neighborhood + price + bedrooms
             
             // Pontos extras condicionais
             CASE WHEN i_busca.tipo IS NOT NULL AND i_busca.tipo = i_oferece.tipo THEN 5 ELSE 0 END AS score_tipo,
             CASE WHEN i_busca.area IS NOT NULL AND i_oferece.area >= i_busca.area THEN 5 ELSE 0 END AS score_area,
             CASE WHEN i_busca.vagas IS NOT NULL AND i_oferece.vagas >= i_busca.vagas THEN 5 ELSE 0 END AS score_vagas,
             CASE WHEN i_busca.frente_mar = true AND i_oferece.frente_mar = true THEN 10 ELSE 0 END AS score_mar,
             CASE WHEN i_busca.condominio = true AND i_oferece.condominio = true THEN 5 ELSE 0 END AS score_cond,
             CASE WHEN i_busca.sol IS NOT NULL AND i_busca.sol = i_oferece.sol THEN 5 ELSE 0 END AS score_sol,
             CASE WHEN i_busca.perto_praia = true AND i_oferece.perto_praia = true THEN 5 ELSE 0 END AS score_praia
             
        WITH comprador, m_busca, i_busca, vendedor, m_oferece, i_oferece, b_oferece,
             (score_base + score_tipo + score_area + score_vagas + score_mar + score_cond + score_sol + score_praia) AS score_final
             
        // -------------------------------------------------------------
        // 3. RETORNO DOS DADOS ORDENADOS PELO MELHOR MATCH
        // -------------------------------------------------------------
        RETURN 
            comprador.nome AS buyer_name,
            comprador.telefone AS buyer_phone,
            m_busca.texto AS buyer_text,
            vendedor.nome AS seller_name,
            vendedor.telefone AS seller_phone,
            m_oferece.texto AS seller_text,
            score_final AS score
        ORDER BY score_final DESC
        """
        
        with self.driver.session() as session:
            result = session.run(query)
            
            # Aqui formatamos exatamente como o exportador do projeto espera
            opportunities = []
            for record in result:
                opportunities.append({
                    "buyer": {
                        "name": record["buyer_name"],
                        "phone": record["buyer_phone"],
                        "raw_text": record["buyer_text"]
                    },
                    "seller": {
                        "name": record["seller_name"],
                        "phone": record["seller_phone"],
                        "raw_text": record["seller_text"]
                    },
                    "score": record["score"]
                })
            return opportunities


if __name__ == "__main__":
    cliente = GraphClient()
    cliente.test_connection()
    cliente.close()