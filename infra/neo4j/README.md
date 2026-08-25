# Neo4j local

This is a standalone local Neo4j service. It does not recreate or replace the
existing PostgreSQL or RabbitMQ containers.

## Start

Create the root `.env` from `.env.example` and set `NEO4J_PASSWORD` locally.
Then run:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Neo4j is available at:

```text
Bolt:    bolt://localhost:7687
Browser: http://localhost:7474
```

## Apply identity constraints

The bootstrap is repeatable and does not delete graph data. With the password
available in the local shell, run:

```bash
docker exec sentinel-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -f /var/lib/neo4j/import/constraints.cypher
```

On PowerShell, use `$env:NEO4J_PASSWORD` in place of `$NEO4J_PASSWORD`.

The bootstrap creates uniqueness constraints for `Pessoa.person_id`,
`Mensagem.id`, `Demanda.demand_id`, `Oferta.offer_id`, and `Imovel.id`.
`Bairro.nome` intentionally has no uniqueness constraint until its
canonicalization and alias policy are defined.
