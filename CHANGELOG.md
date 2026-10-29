# Changelog - Sentinel Bot

Todas as alterações notáveis deste projeto serão documentadas neste arquivo.
Baseado no formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [2.0.0] - 2026-10-29 — Release Oficial `feat/grafos`

> 🚀 **Arquitetura Reativa de Alta Performance: RabbitMQ, Neo4j Graph Database, PostgreSQL e Snapshot/Diff de Inventário.**

### Adicionado

- **Camada de Mensageria Orientada a Eventos (EDA) via RabbitMQ**:
  - `wpp-collector/rabbitmq.js`: Publica eventos na fila `raw_messages` imediatamente após persistência no PostgreSQL.
  - `intel-engine/engine.py`: Reescrito como consumidor RabbitMQ via `pika` com `basic_qos(prefetch_count=1)` (fair dispatch).
  - `wpp-egress/main.js`: Reescrito como consumidor `amqplib` escutando a fila `opportunities_queue`, disparando mensagens no WhatsApp instantaneamente sem polling.
- **Grafo de Conhecimento Imobiliário via Neo4j**:
  - Infraestrutura local provisionada via Docker (`neo4j:5.26.0-community`) com volume persistente em `docker-compose.neo4j.yml`.
  - Script de constraints e índices de unicidade (`infra/neo4j/constraints.cypher`) para `Pessoa.person_id`, `Mensagem.id`, `Demanda.demand_id`, `Oferta.offer_id` e `Imovel.id`.
  - Modelagem explícita de `Demanda` e `Oferta` intermediadas por vizinhanças compartilhadas (`Bairro`), substituindo projeções diretas.
  - Query Cypher de matching multi-critério calculando score ponderado baseado em: compatibilidade de bairro (+10), preço dentro da margem (+10), quartos adequados (+10), tipologia (+5), área (+5), vagas (+5), frente mar (+10), condomínio (+5), posição solar (+5) e proximidade com praia (+5).
- **Worker de Sincronização de Inventário (`inventory_sync_worker.py`)**:
  - Processo de background dedicado com controle de ciclo de vida e graceful shutdown (SIGINT/SIGTERM).
  - Algoritmo de snapshot/diff que compara fingerprints SHA-256 e sincroniza apenas alterações reais no grafo.
  - Tabela de controle `inventory_sync_state` no PostgreSQL.
- **Suporte a Tipos Numéricos Seguros**:
  - Sanitização de tipos `decimal.Decimal` do PostgreSQL para `float`/`int` no `inventory_adapter.py` e `neo4j_client.py`, prevenindo falhas de serialização no protocolo Bolt.
- **Suíte de Testes Automatizados**:
  - 64 testes unitários cobrindo entrega de engine, contratos de schema, sincronização de inventário, adaptadores e regras de matching.
  - Teste de integração real com o Neo4j (`test_neo4j_integration.py`).

### Alterado

- `ecosystem.config.js`: Corrigido o caminho do interpretador Python para `intel-engine/.venv/bin/python`, garantindo execução correta de `sentinel-engine` e `sentinel-inventory-sync` no PM2.
- `database.py`: Substituído o padrão de conexão única por pool `SimpleConnectionPool` e centralização de configuração em `runtime_config.py`.
- `cleaner.py` e `purge_user.py`: Adaptados para operar em cascata simultaneamente no PostgreSQL e Neo4j (remoção com `DETACH DELETE`).

### Removido

- Código legado de matching estático via memória (`matcher.py`).
- Código legado de exportação e leitura de arquivos JSONL (`egest.py`, `data/*.jsonl`).
- Loops de polling com `while True` e `setInterval`.

---

## [1.7.0] - 2026-07-09

- Primeira versão da separação em 3 processos no PM2 (`wpp-collector`, `intel-engine`, `wpp-egress`).
- Adição da priorização de imóveis próprios por DM direta.
- Integração preliminar com Neo4j AuraDB.
