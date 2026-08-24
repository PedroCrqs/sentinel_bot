import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)

URI = os.getenv("NEO4J_URI", "")
USER = os.getenv("NEO4J_USERNAME", "")
PASSWORD = os.getenv("NEO4J_PASSWORD", "")

AUTH = (USER, PASSWORD)

INVALID_IDENTITIES = {"", "desconhecido"}


def _require_identity(value, field_name: str):
    """Validate and normalize an identity before sending it to Neo4j."""
    if value is None:
        raise ValueError(f"{field_name} é obrigatório para projetar no Neo4j")

    if isinstance(value, str):
        identity = value.strip()
        if not identity or identity.lower() in INVALID_IDENTITIES:
            raise ValueError(f"{field_name} inválido para projeção Neo4j: {value!r}")
        return identity

    if not value:
        raise ValueError(f"{field_name} inválido para projeção Neo4j: {value!r}")

    return value


def _resolve_property_id(ad_data: dict, original: dict, message_id: str) -> str:
    """Resolve the current projection identity for an Imovel.

    Inventory properties must use the PostgreSQL ImovelID. External ads keep
    the temporary message-based identity until Oferta and Imovel are split.
    """
    inventory_property = original.get("source") == "inventory"
    if inventory_property:
        return _require_identity(original.get("imovel_id"), "ImovelID do inventário")

    explicit_id = original.get("imovel_id")
    if explicit_id is not None:
        return _require_identity(explicit_id, "ImovelID")

    return _require_identity(f"{message_id}_imovel", "identidade provisória do Imovel")

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
        original = ad_data.get("original_content") or {}

        person_id = _require_identity(
            original.get("author_id"), "author_id/Pessoa.person_id"
        )
        message_id = _require_identity(
            original.get("message_id"), "message_id/Mensagem.id"
        )
        property_id = _resolve_property_id(ad_data, original, message_id)
        
        bairros = ad_data.get("neighborhood", [])
        bairro_principal = bairros[0] if bairros else "Desconhecido"

        query = """
        // Pessoa e Bairro
        MERGE (p:Pessoa {person_id: $person_id})
        ON CREATE SET p.nome = $nome, p.telefone = $telefone
        SET p.nome = CASE WHEN $nome IS NOT NULL AND trim($nome) <> '' THEN $nome ELSE p.nome END,
            p.telefone = CASE WHEN $telefone IS NOT NULL AND trim($telefone) <> '' THEN $telefone ELSE p.telefone END
        
        MERGE (b:Bairro {nome: $bairro})
        
        // Mensagem
        MERGE (m:Mensagem {id: $msg_id})
        SET m.texto = $texto, m.timestamp = $ts
        MERGE (p)-[:ENVIOU]->(m)
        
        // Imóvel
        MERGE (i:Imovel {id: $property_id})
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

        intent = str(ad_data.get("intent", "")).lower()
        
        if intent in ["buy", "buying", "compra", "comprar", "busca", "buscando", "interesse", "demand", "procura", "procurando", "demanda"]:
            query += "\nMERGE (m)-[:BUSCA]->(i)"
        else:
            query += "\nMERGE (m)-[:OFERECE]->(i)"

        with self.driver.session() as session:
            session.run(query, 
                person_id=person_id,
                telefone=original.get("author_phone"),
                nome=original.get("author_name", "Desconhecido"),
                msg_id=message_id,
                property_id=property_id,
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
        query = """
        MATCH (comprador:Pessoa)-[:ENVIOU]->(m_busca:Mensagem)-[:BUSCA]->(i_busca:Imovel)-[:LOCALIZADO_EM]->(b_busca:Bairro)
        MATCH (vendedor:Pessoa)-[:ENVIOU]->(m_oferece:Mensagem)-[:OFERECE]->(i_oferece:Imovel)-[:LOCALIZADO_EM]->(b_oferece:Bairro)
        
        WHERE comprador.person_id <> vendedor.person_id
          AND (b_busca.nome = 'Desconhecido' OR b_busca.nome = b_oferece.nome)
          AND (i_busca.preco IS NULL OR (i_oferece.preco >= (i_busca.preco * 0.80) AND i_oferece.preco <= (i_busca.preco + 50000)))
          AND (i_busca.quartos IS NULL OR i_oferece.quartos >= i_busca.quartos)
          AND (i_busca.frente_mar = false OR i_oferece.frente_mar = true)

        WITH comprador, m_busca, i_busca, b_busca, vendedor, m_oferece, i_oferece, b_oferece,
             (10 + 10 + 5) AS score_base, 
             CASE WHEN i_busca.tipo IS NOT NULL AND i_busca.tipo = i_oferece.tipo THEN 5 ELSE 0 END AS score_tipo,
             CASE WHEN i_busca.area IS NOT NULL AND i_oferece.area >= i_busca.area THEN 5 ELSE 0 END AS score_area,
             CASE WHEN i_busca.vagas IS NOT NULL AND i_oferece.vagas >= i_busca.vagas THEN 5 ELSE 0 END AS score_vagas,
             CASE WHEN i_busca.frente_mar = true AND i_oferece.frente_mar = true THEN 10 ELSE 0 END AS score_mar,
             CASE WHEN i_busca.condominio = true AND i_oferece.condominio = true THEN 5 ELSE 0 END AS score_cond,
             CASE WHEN i_busca.sol IS NOT NULL AND i_busca.sol = i_oferece.sol THEN 5 ELSE 0 END AS score_sol,
             CASE WHEN i_busca.perto_praia = true AND i_oferece.perto_praia = true THEN 5 ELSE 0 END AS score_praia
             
        WITH comprador, m_busca, i_busca, vendedor, m_oferece, i_oferece, b_oferece,
             (score_base + score_tipo + score_area + score_vagas + score_mar + score_cond + score_sol + score_praia) AS score_final
             
        RETURN 
            comprador.nome AS buyer_name,
            comprador.telefone AS buyer_phone,
            m_busca.id AS buyer_message_id,
            m_busca.texto AS buyer_text,
            vendedor.nome AS seller_name,
            vendedor.telefone AS seller_phone,
            m_oferece.id AS seller_message_id,
            i_oferece.id AS matched_imovel_id,
            m_oferece.texto AS seller_text,
            score_final AS score
        ORDER BY score_final DESC
        """
        
        with self.driver.session() as session:
            result = session.run(query)
            
            opportunities = []
            for record in result:
                opportunities.append({
                    "buyer_message_id": record["buyer_message_id"],
                    "seller_message_id": record["seller_message_id"],
                    "matched_imovel_id": record["matched_imovel_id"],
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
