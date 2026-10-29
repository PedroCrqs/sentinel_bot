// Inspection only: review these counts before executing the DELETE statements.
MATCH ()-[r:BUSCA]->(:Imovel)
RETURN 'legacy_busca_relationships' AS item, count(r) AS count;

MATCH ()-[r:OFERECE]->(:Imovel)
RETURN 'legacy_oferece_relationships' AS item, count(r) AS count;

MATCH (i:Imovel {legacy_projection: true})
WHERE NOT (i)<-[:REFERE_SE_A]-(:Oferta)
RETURN 'identifiable_demand_projection_properties' AS item, count(i) AS count;

// Remove only the two explicitly legacy relationship types.
MATCH ()-[r:BUSCA]->(:Imovel)
DELETE r;

MATCH ()-[r:OFERECE]->(:Imovel)
DELETE r;

// Remove only demand-only projection nodes created by the old matcher.
// Offer/inventory properties are protected by the REFERE_SE_A check.
MATCH (i:Imovel {legacy_projection: true})
WHERE NOT (i)<-[:REFERE_SE_A]-(:Oferta)
DETACH DELETE i;
