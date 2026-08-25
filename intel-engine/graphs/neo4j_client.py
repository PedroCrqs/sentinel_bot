from neo4j import GraphDatabase
from runtime_config import required_config

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


def _is_buying(ad_data: dict) -> bool:
    return str(ad_data.get("intent", "")).lower() in {
        "buy",
        "buying",
        "compra",
        "comprar",
        "busca",
        "buscando",
        "interesse",
        "demand",
        "procura",
        "procurando",
        "demanda",
    }


def _resolve_demand_id(original: dict, message_id: str) -> str:
    """A purchase message currently represents one demand."""
    return _require_identity(original.get("demand_id", message_id), "Demanda.demand_id")


def _resolve_offer_id(original: dict, message_id: str) -> str:
    """Resolve an offer identity without using phone or description text."""
    if original.get("source") == "inventory":
        property_id = _require_identity(
            original.get("imovel_id"), "ImovelID do inventário"
        )
        return _require_identity(f"self-offer:{property_id}", "Oferta.offer_id")

    return _require_identity(original.get("offer_id", message_id), "Oferta.offer_id")

class GraphClient:
    def __init__(self):
        uri = required_config("NEO4J_URI")
        user = required_config("NEO4J_USERNAME")
        password = required_config("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

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
        buying = _is_buying(ad_data)
        property_id = _resolve_property_id(ad_data, original, message_id)
        demand_id = _resolve_demand_id(original, message_id) if buying else None
        offer_id = _resolve_offer_id(original, message_id) if not buying else None
        
        bairros = [
            str(bairro).strip()
            for bairro in (ad_data.get("neighborhood") or [])
            if bairro and str(bairro).strip().lower() != "desconhecido"
        ]
        bairro_principal = bairros[0] if bairros else "Desconhecido"

        query = """
        // Pessoa e Mensagem
        MERGE (p:Pessoa {person_id: $person_id})
        ON CREATE SET p.nome = $nome, p.telefone = $telefone
        SET p.nome = CASE WHEN $nome IS NOT NULL AND trim($nome) <> '' THEN $nome ELSE p.nome END,
            p.telefone = CASE WHEN $telefone IS NOT NULL AND trim($telefone) <> '' THEN $telefone ELSE p.telefone END
        
        // Mensagem
        MERGE (m:Mensagem {id: $msg_id})
        SET m.texto = $texto, m.timestamp = $ts
        MERGE (p)-[:ENVIOU]->(m)
        
        """

        if buying:
            query += """
            // Modelo novo: a compra expressa uma Demanda, não um Imovel.
            MERGE (d:Demanda {demand_id: $demand_id})
            SET d.price = $preco,
                d.bedrooms = $quartos,
                d.area = $area,
                d.parking_spots = $vagas,
                d.seafront = $frente_mar,
                d.condominium = $condominio,
                d.sun_type = $sol,
                d.nearbeach = $perto_praia,
                d.property_type = $tipo,
                d.status = 'ACTIVE'
            MERGE (p)-[:CRIOU]->(d)
            MERGE (m)-[:EXPRESSA]->(d)
            FOREACH (neighborhood IN $bairros |
                MERGE (db:Bairro {nome: neighborhood})
                MERGE (d)-[:BUSCA_EM]->(db)
            )

            // LEGACY: mantido somente para o matcher atual. Será removido
            // quando match_opportunities() passar a usar Demanda diretamente.
            MERGE (legacy_i:Imovel {id: $property_id})
            SET legacy_i.tipo = $tipo,
                legacy_i.property_type = $tipo,
                legacy_i.preco = $preco,
                legacy_i.quartos = $quartos,
                legacy_i.area = $area,
                legacy_i.vagas = $vagas,
                legacy_i.frente_mar = $frente_mar,
                legacy_i.condominio = $condominio,
                legacy_i.sol = $sol,
                legacy_i.perto_praia = $perto_praia,
                legacy_i.legacy_projection = true
            MERGE (legacy_b:Bairro {nome: $bairro})
            MERGE (legacy_i)-[:LOCALIZADO_EM]->(legacy_b)
            MERGE (m)-[:BUSCA]->(legacy_i)
            """
        else:
            query += """
            // Modelo novo: a venda cria uma Oferta que referencia um Imovel.
            MERGE (i:Imovel {id: $property_id})
            SET i.property_id = $property_id,
                i.property_type = $tipo,
                i.tipo = $tipo,
                i.quartos = $quartos,
                i.area = $area,
                i.vagas = $vagas,
                i.frente_mar = $frente_mar,
                i.condominio = $condominio,
                i.sol = $sol,
                i.perto_praia = $perto_praia,
                // preco é legado para o matcher atual; o preço canônico fica na Oferta.
                i.preco = $preco
            MERGE (b:Bairro {nome: $bairro})
            MERGE (i)-[:LOCALIZADO_EM]->(b)
            MERGE (o:Oferta {offer_id: $offer_id})
            ON CREATE SET o.created_at = $created_at
            SET o.price = $preco,
                o.status = 'ACTIVE'
            MERGE (p)-[:PUBLICOU]->(o)
            MERGE (m)-[:ORIGINA]->(o)
            MERGE (o)-[:REFERE_SE_A]->(i)

            // LEGACY: mantido para o matcher atual.
            MERGE (m)-[:OFERECE]->(i)
            """

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
                bairro=bairro_principal,
                bairros=bairros,
                demand_id=demand_id,
                offer_id=offer_id,
                created_at=original.get("timestamp", 0)
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
