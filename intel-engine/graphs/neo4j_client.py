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


def _inventory_offer_status(ad_data: dict) -> str:
    status = ad_data.get("status")
    if status == "available":
        return "ACTIVE"
    if status == "unavailable":
        return "INACTIVE"
    raise ValueError(f"Unknown canonical inventory status: {status!r}")

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
        property_id = _resolve_property_id(ad_data, original, message_id) if not buying else None
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
                o.status = $offer_status
            MERGE (p)-[:PUBLICOU]->(o)
            MERGE (m)-[:ORIGINA]->(o)
            MERGE (o)-[:REFERE_SE_A]->(i)

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
                created_at=original.get("timestamp", 0),
                offer_status=(
                    _inventory_offer_status(ad_data)
                    if original.get("source") == "inventory"
                    else "ACTIVE"
                )
            )

    def deactivate_inventory_property(self, property_id):
        """Deactivate an inventory offer without deleting its property node."""
        property_id = _require_identity(property_id, "ImovelID do inventÃ¡rio")
        query = """
        MATCH (i:Imovel {id: $property_id})
        OPTIONAL MATCH (o:Oferta {offer_id: $offer_id})-[:REFERE_SE_A]->(i)
        SET o.status = 'INACTIVE'
        """
        with self.driver.session() as session:
            session.run(
                query,
                property_id=property_id,
                offer_id=f"self-offer:{property_id}",
            )

    def match_opportunities(self):
        query = """
        // Novo modelo: Demanda x Oferta através da vizinhança compartilhada.
        // As mensagens/pessoas abaixo existem apenas para contexto e auditoria.
        MATCH (d:Demanda)-[:BUSCA_EM]->(b:Bairro)<-[:LOCALIZADO_EM]-(i:Imovel)<-[:REFERE_SE_A]-(o:Oferta)
        MATCH (comprador:Pessoa)-[:CRIOU]->(d)
        MATCH (m_busca:Mensagem)-[:EXPRESSA]->(d)
        MATCH (vendedor:Pessoa)-[:PUBLICOU]->(o)
        MATCH (m_oferece:Mensagem)-[:ORIGINA]->(o)

        WHERE d.status = 'ACTIVE'
          AND o.status = 'ACTIVE'
          AND comprador.person_id <> vendedor.person_id
          AND (d.price IS NULL OR (o.price IS NOT NULL AND o.price <= d.price))
          AND (d.bedrooms IS NULL OR (i.quartos IS NOT NULL AND i.quartos >= d.bedrooms))
          AND (coalesce(d.seafront, false) = false OR i.frente_mar = true)

        // collect evita duplicar o mesmo par quando a demanda possui vários bairros.
        WITH d, o, i, comprador, vendedor, m_busca, m_oferece,
             collect(DISTINCT b.nome) AS matched_neighborhoods

        // Tipo permanece preferência (comportamento anterior), não hard constraint.
        // Preço/quartos só pontuam quando os dois lados possuem o dado.
        WITH d, o, i, comprador, vendedor, m_busca, m_oferece, matched_neighborhoods,
             CASE WHEN d.price IS NOT NULL AND o.price IS NOT NULL THEN 10 ELSE 0 END
                 + CASE WHEN d.bedrooms IS NOT NULL AND i.quartos IS NOT NULL THEN 10 ELSE 0 END
                 + 5 AS score_base,
             CASE WHEN d.property_type IS NOT NULL AND i.property_type IS NOT NULL
                       AND d.property_type = i.property_type THEN 5 ELSE 0 END AS score_type,
             CASE WHEN d.area IS NOT NULL AND i.area IS NOT NULL AND i.area >= d.area
                       THEN 5 ELSE 0 END AS score_area,
             CASE WHEN d.parking_spots IS NOT NULL AND i.vagas IS NOT NULL
                       AND i.vagas >= d.parking_spots THEN 5 ELSE 0 END AS score_parking,
             CASE WHEN d.seafront = true AND i.frente_mar = true THEN 10 ELSE 0 END AS score_seafront,
             CASE WHEN d.condominium = true AND i.condominio = true THEN 5 ELSE 0 END AS score_condominium,
             CASE WHEN d.sun_type IS NOT NULL AND i.sol IS NOT NULL
                       AND d.sun_type = i.sol THEN 5 ELSE 0 END AS score_sun,
             CASE WHEN d.nearbeach = true AND i.perto_praia = true THEN 5 ELSE 0 END AS score_nearbeach

        WITH d, o, i, comprador, vendedor, m_busca, m_oferece, matched_neighborhoods,
             score_base, score_type, score_area, score_parking, score_seafront,
             score_condominium, score_sun, score_nearbeach,
             score_base + score_type + score_area + score_parking + score_seafront
                 + score_condominium + score_sun + score_nearbeach AS score_final

        RETURN
            d.demand_id AS demand_id,
            o.offer_id AS offer_id,
            i.id AS property_id,
            i.id AS matched_imovel_id,
            comprador.nome AS buyer_name,
            comprador.telefone AS buyer_phone,
            m_busca.id AS buyer_message_id,
            m_busca.texto AS buyer_text,
            vendedor.nome AS seller_name,
            vendedor.telefone AS seller_phone,
            m_oferece.id AS seller_message_id,
            m_oferece.texto AS seller_text,
            matched_neighborhoods,
            d.price AS demand_price,
            d.bedrooms AS demand_bedrooms,
            o.price AS offer_price,
            i.quartos AS property_bedrooms,
            score_base,
            score_type,
            score_area,
            score_parking,
            score_seafront,
            score_condominium,
            score_sun,
            score_nearbeach,
            score_final AS score
        ORDER BY score_final DESC
        """
        
        with self.driver.session() as session:
            result = session.run(query)
            
            opportunities = []
            for record in result:
                matched_neighborhoods = record["matched_neighborhoods"] or []
                opportunities.append({
                    "demand_id": record["demand_id"],
                    "offer_id": record["offer_id"],
                    "property_id": record["property_id"],
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
                    "score": record["score"],
                    "rule_version": "v1",
                    "match_details": {
                        "matched_neighborhood": matched_neighborhoods[0]
                        if matched_neighborhoods else None,
                        "matched_neighborhoods": matched_neighborhoods,
                        "hard_constraints": {
                            "location": True,
                            "price": {
                                "demand_max": record["demand_price"],
                                "offer_price": record["offer_price"],
                            },
                            "bedrooms": {
                                "demand_min": record["demand_bedrooms"],
                                "property": record["property_bedrooms"],
                            },
                        },
                        "score_breakdown": {
                            "base": record["score_base"],
                            "type": record["score_type"],
                            "area": record["score_area"],
                            "parking": record["score_parking"],
                            "seafront": record["score_seafront"],
                            "condominium": record["score_condominium"],
                            "sun": record["score_sun"],
                            "nearbeach": record["score_nearbeach"],
                        },
                    },
                })
            return opportunities


if __name__ == "__main__":
    cliente = GraphClient()
    cliente.test_connection()
    cliente.close()
