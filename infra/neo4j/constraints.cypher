// Canonical identity constraints for the current graph projection.
// Re-running this file is safe and does not delete existing data.

CREATE CONSTRAINT pessoa_person_id_unique IF NOT EXISTS
FOR (p:Pessoa) REQUIRE p.person_id IS UNIQUE;

CREATE CONSTRAINT mensagem_id_unique IF NOT EXISTS
FOR (m:Mensagem) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT demanda_demand_id_unique IF NOT EXISTS
FOR (d:Demanda) REQUIRE d.demand_id IS UNIQUE;

CREATE CONSTRAINT oferta_offer_id_unique IF NOT EXISTS
FOR (o:Oferta) REQUIRE o.offer_id IS UNIQUE;

CREATE CONSTRAINT imovel_id_unique IF NOT EXISTS
FOR (i:Imovel) REQUIRE i.id IS UNIQUE;
