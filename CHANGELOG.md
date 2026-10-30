# Changelog - Sentinel Bot

All notable changes to this project will be documented in this file.
Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.0.0] - 2026-10-29

### English

#### Added

- **Automatic Phone Number Resolution and Extraction Pipeline**:
  - `wpp-collector/ingest.js`: Automatically resolves real phone numbers for WhatsApp users when messages are received from privacy-shielded `@lid` identifiers by leveraging WhatsApp Web client `getContactLidAndPhone` retrieval.
  - Regex-based phone extractor (`extractPhoneFromText`) supporting complete Brazilian phone formats (wa.me links, 11-digit mobile with DDD, 9-digit local, and landlines).
  - `intel-engine/classifier.py` & `intel-engine/normalizer.py`: Recovers and assigns extracted phone numbers directly to `Message` and `NormalizedAd` entities when author phone is an opaque LID or unknown.
  - `intel-engine/graphs/neo4j_client.py`: Enriches and persists verified phone numbers into `(p:Pessoa).telefone`.
  - `wpp-egress/main.js`: Formats phone numbers cleanly (`+55 (DD) 9XXXX-XXXX`) and generates direct clickable WhatsApp links (`https://wa.me/55...`), with proactive fallback LID resolution.
- **Owned Property Owner Contact Propagation (`database.py`, `inventory_adapter.py`, `inventory_sync.py`)**:
  - `public.proprietarios` integration: `get_available_properties()` and `get_inventory_snapshot()` now join with `public.proprietarios` to propagate `proprietario_nome` and `proprietario_telefone` into Majesto inventory offers.
  - Fixes missing seller phone numbers on self-owned property opportunity dispatches.
- **Entities Knowledge Base Expansion (`entities.json`)**:
  - Added 50 canonical neighborhoods and 224 condominiums/ventures mapped from `public.bairros`, `public.condominios` and historical `raw_messages`.
  - Expanded `NEIGHBORHOOD_PARENT` from 4 to 169 mappings linking all known condominiums and sub-neighborhoods to their canonical parent neighborhoods.

- **Event-Driven Architecture (EDA) with RabbitMQ**:
  - `wpp-collector/rabbitmq.js`: Publishes raw message events to `raw_messages` queue immediately upon persisting to PostgreSQL.
  - `intel-engine/engine.py`: Event-driven consumer using `pika` with `basic_qos(prefetch_count=1)` (fair dispatch).
  - `wpp-egress/main.js`: Reactive consumer listening on `opportunities_queue`; dispatches notifications instantly via WhatsApp without polling.
  - Rate-limit control on partner group dispatch (`MAX_GROUP_OPPS_PER_HOUR`, default 10 msgs/hour) to prevent spam bans.
- **Neo4j Graph Database Integration (Local Docker `neo4j:5.26.0-community`)**:
  - Direct Cypher projection of `Demanda`, `Oferta`, `Imovel`, `Pessoa`, and `Bairro`.
  - Strict uniqueness constraints provisioned via `infra/neo4j/constraints.cypher`.
  - Multi-criteria semantic scoring query matching demands with offers.
- **Dedicated Inventory Snapshot/Diff Sync Worker (`inventory_sync_worker.py`)**:
  - Autonomous long-running worker syncing `public.imoveis` from PostgreSQL with Neo4j.
  - Fingerprint-based state tracking in `public.inventory_sync_state`.
- **Cleaner Pipeline Overhaul & Automated Engine Daemon**:
  - Background daemon thread integrated directly into `engine.py`, executing every 6 hours automatically.
  - Strict 90-day expiration window for external property offers.
  - Strict 15-day expiration window for buyer demands.
  - Automated purge of orphaned `Imovel` and `Pessoa` nodes and duplicates across PostgreSQL and Neo4j, while strictly protecting Majesto inventory properties.
- **Historical Backfill Script (`backfill_history.py`)**:
  - Loads 90-day historical messages from PostgreSQL, classifies and normalizes entities, populates Neo4j, and marks records as `PROCESSED`.

#### Changed

- **Mandatory Price Compatibility in Matcher**: Location alone no longer qualifies an opportunity. Both demand and offer must specify a price, and the offer price must fall within a valid price window: it must not exceed the buyer budget **and** must be at least 70% of it (`d.price * 0.70 <= o.price <= d.price`). Offers priced more than 30% below the buyer's ceiling are rejected to avoid irrelevant low-budget matches.
- **Strict Opportunity Qualification in Engine**: Partner opportunities are evaluated and filtered directly in `intel-engine/engine.py` (only matches with score strictly greater than 50, `score > 50`, are saved and published to RabbitMQ). Discarded opportunities are logged within the engine, maintaining `wpp-egress` purely focused on WhatsApp dispatch.
- **Heavy Prioritization of Majesto Inventory**: Own properties from `public.imoveis` receive a +35 priority score bonus and route exclusively to priority private DM (`PRIORITY_CONTACT_ID`) with **no hourly rate limit**.
- **Sanitized Numeric Types**: Converted PostgreSQL `decimal.Decimal` to `float` across adapters to prevent Bolt serialization exceptions.

#### Fixed

- **Database Connection Pool Leak in Cleaner & Backfill (`cleaner.py`, `backfill_history.py`)**: `purge_old_data_sql` and `load_candidate_messages` acquired PostgreSQL connections from the pool but never released them via `release_db_connection()`. In long-running engine deployments, this exhausted the pool (`maxconn=10`) every ~54 hours and stalled all database lookups. Fixed by wrapping execution in `try...finally: release_db_connection(conn)`.
- **False Self-Inventory Privilege Spoofing Prevention (`engine.py`, `wpp-egress/main.js`)**: Replaced loose pushname matching (`"majesto" in seller_name`) with strict identity verification (`offer_id.startswith("self-offer:")`, `opp["is_self"] = True`, or `seller_id == "system:majesto"`), preventing external third-party brokers with "Majesto" in their WhatsApp profile from spoofing internal inventory privileges.
- **Atomic Opportunity Claim in Egress (`wpp-egress/main.js`)**: Implemented atomic reservation using `UPDATE opportunities SET dispatch_status = 'SENDING' WHERE opportunity_id = $1 AND dispatch_status = 'PENDING' RETURNING match_details` before dispatch, preventing duplicate message sends and race conditions.
- **RabbitMQ Egress Consumer Timeout & Lifecycle Handling (`wpp-egress/main.js`)**: Capped continuous group rate limit sleeps to safe intervals and added connection `close`/`error` handlers exiting with code 1 for automated PM2 resurrection.
- **Poison Message Infinite Loop Protection (`engine.py`)**: Added detection of deterministic errors and repeated failures (`method.redelivered`) on RabbitMQ consumption, discarding unprocessable messages without requeueing to prevent 100% CPU lockups.
- **Inventory Node Protection & Purge User Integrity (`cleaner.py`, `purge_user.py`)**: Tagged inventory properties with `source = 'inventory'` in Neo4j and updated cleaner queries to protect them explicitly. Fixed `purge_user.py` to match `p.person_id`, cascade delete associated demands, offers, and opportunities, and release database connections.
- **Repository Hygiene (`intel-engine/requirements.txt`)**: Converted `requirements.txt` from UTF-16 LE CRLF to standard UTF-8 LF.

- **Price Normalization Flexibility without Currency Prefix (`normalizer.py`)**:
  - `extract_price()` previously strictly demanded literal `R$` symbols, failing on common broker patterns such as `"por 800k"`, `"até 800 mil"`, `"800k"`, `"1.8M"`, and formatted thousands (`800.000`).
  - Added multi-pattern price extractor supporting prefixes (`valor`, `preco`, `ate`, `por`, `teto`, `orcamento`), multipliers (`k`, `mil`, `mi`, `m`, `milhão`, `milhões`), and formatted dot-separated thousands (threshold >= 50,000).
- **Condominium Neighborhood Masking and Locality Resolution (`normalizer.py`)**:
  - Resolves condominiums directly to their parent canonical neighborhoods (e.g., `"maayan"` -> `["BARRA OLIMPICA", "BARRA"]`, `"peninsula"` -> `["BARRA"]`, `"barra sunday"` -> `["RECREIO"]`) before masking to prevent empty neighborhood lists (`neighborhood: []`) and unmatchable `DESCONHECIDO` graph projections.
  - Implemented dual-affiliation mapping for Maayan and Cidade Jardim across Barra Olímpica and Barra da Tijuca.

- **Canonical Neighborhood Taxonomy & Alias Mapping (`normalizer.py`, `inventory_sync.py`, `graphs/neo4j_client.py`)**: The NLP normalizer mapped WhatsApp demand messages to canonical alias tokens (`"Barra da Tijuca"` -> `"BARRA"`, `"Recreio dos Bandeirantes"` -> `"RECREIO"`, `"Barra Olímpica"` -> `"BARRA OLIMPICA"`), whereas the PostgreSQL inventory projection (`bairros.nome`) was creating distinct nodes with the raw database names (`"BARRA DA TIJUCA"`, `"RECREIO DOS BANDEIRANTES"`, `"BARRA OLÍMPICA"`). This disjoint taxonomy caused 85% of the Majesto inventory to have zero spatial overlap with incoming broker demands, completely preventing matches. Fixed by adding `canonical_neighborhood()` and `_normalize_neighborhood()` across the projection pipeline, and migrating existing Neo4j edges to unified canonical `Bairro` nodes.
- **Semantic Feature Extraction from Property Description (`inventory_sync.py`)**: Previously, `property_to_inventory_ad()` left `seafront=None`, `nearbeach=False`, and `condominium=False`, ignoring the property description. In addition, when buyers required seafront properties (`d.seafront = true`), the matcher strictly rejected inventory properties. Now, `NormalizedAd` extracts `seafront` (e.g. "frontal mar", "frente mar"), `nearbeach`, `condominium`, and normalized solar orientation (`sun_type`) directly from `public.imoveis.descricao`, properly scoring and qualifying inventory opportunities.
- **PostgreSQL Constraint Relaxation on `opportunities.seller_message_id` (`migrations/004_relax_opportunity_seller_message_reference.sql`)**: Relaxes foreign key `opportunities_seller_message_id_fkey` on `raw_messages`. Owned inventory offers use synthetic `seller_message_id` (`self-<property_id>`) that do not exist in WhatsApp raw messages; the previous FK caused `ForeignKeyViolation` exceptions whenever a Majesto match was inserted, creating endless message retry loops in RabbitMQ.
- **Multi-Neighborhood Graph Linking for Properties (`graphs/neo4j_client.py`)**: Property nodes now link to all detected locations (e.g., sub-neighborhoods like `CIDADE JARDIM` alongside parent `BARRA OLIMPICA`) via Cypher `FOREACH`, allowing matches on both broad and specific locality queries.
- **Case-Insensitive Property Type Normalization in `graphs/neo4j_client.py`**: Ensures `property_type` (`"APARTAMENTO"`, `"CASA"`, `"COBERTURA"`) matches identically across demands and inventory offers.

---

### Português

#### Adicionado

- **Pipeline de Resolução e Extração Automática de Telefones**:
  - `wpp-collector/ingest.js`: Resolução automática de números reais de telefone quando a mensagem é originada de identificadores ocultos `@lid`, utilizando `getContactLidAndPhone` do cliente WhatsApp Web.
  - Extrator regex inteligente (`extractPhoneFromText`) com suporte completo aos formatos brasileiros (links wa.me, celulares com DDD de 11 dígitos, locais de 9 dígitos e telefones fixos).
  - `intel-engine/classifier.py` e `intel-engine/normalizer.py`: Recuperação e injeção automática de números extraídos do texto nas entidades `Message` e `NormalizedAd` quando o telefone do autor for um LID.
  - `intel-engine/graphs/neo4j_client.py`: Enriquecimento e persistência no nó `(p:Pessoa).telefone`.
  - `wpp-egress/main.js`: Formatação padronizada de telefones (`+55 (DD) 9XXXX-XXXX`) e geração automática de links clicáveis do WhatsApp (`https://wa.me/55...`), com resolução reativa de LIDs.
- **Propagação do Contato de Proprietários do Inventário Próprio (`database.py`, `inventory_adapter.py`, `inventory_sync.py`)**:
  - Integração com `public.proprietarios`: `get_available_properties()` e `get_inventory_snapshot()` realizam `LEFT JOIN` com `public.proprietarios` para carregar `proprietario_nome` e `proprietario_telefone` nas ofertas do inventário próprio.
  - Garante que oportunidades de imóveis próprios Majesto cheguem acompanhadas do telefone de contato do proprietário.
- **Expansão da Base de Entidades Imobiliárias (`entities.json`)**:
  - Inclusão de 50 bairros canônicos e 224 condomínios/empreendimentos mapeados a partir de `public.bairros`, `public.condominios` e mensagens históricas de `raw_messages`.
  - Expansão de `NEIGHBORHOOD_PARENT` de 4 para 169 mapeamentos associando todos os condomínios aos seus respectivos bairros canônicos.

- **Arquitetura Orientada a Eventos (EDA) via RabbitMQ**:
  - `wpp-collector/rabbitmq.js`: Publica eventos na fila `raw_messages` imediatamente após persistir no PostgreSQL.
  - `intel-engine/engine.py`: Consumidor reativo com `pika` e `basic_qos(prefetch_count=1)` (fair dispatch).
  - `wpp-egress/main.js`: Consumidor reativo na fila `opportunities_queue`; dispara notificações no WhatsApp instantaneamente sem polling.
  - Limitador de vazão para o grupo de parceiros (`MAX_GROUP_OPPS_PER_HOUR`, padrão 10 msgs/hora) para proteção contra bloqueios por spam.
- **Integração com Banco em Grafo Neo4j (Docker Local `neo4j:5.26.0-community`)**:
  - Projeção Cypher direta de nós `Demanda`, `Oferta`, `Imovel`, `Pessoa` e `Bairro`.
  - Constraints e índices de unicidade provisionados via `infra/neo4j/constraints.cypher`.
  - Algoritmo de matching semântico multi-critério calculando pontuação ponderada.
- **Worker Dedicado de Sincronização de Inventário (`inventory_sync_worker.py`)**:
  - Processo de background autônomo que sincroniza a tabela `public.imoveis` com o Neo4j.
  - Rastreamento por fingerprints SHA-256 na tabela `public.inventory_sync_state`.
- **Reformulação do Pipeline de Limpeza & Daemon Automatizado no Engine**:
  - Thread daemon em segundo plano integrada diretamente ao `engine.py`, executando a cada 6 horas automaticamente.
  - Janela estrita de expiração de **90 dias** para ofertas de imóveis de terceiros.
  - Janela estrita de expiração de **15 dias** para demandas de compradores.
  - Expurgo automatizado de nós órfãos (`Imovel` e `Pessoa`) e oportunidades antigas no Neo4j e PostgreSQL, protegendo estritamente o inventário Majesto.
- **Script de Carga e Backfill Histórico (`backfill_history.py`)**:
  - Carrega mensagens dos últimos 90 dias do PostgreSQL, processa via PLN spaCy, normaliza entidades, projeta no Neo4j e atualiza status no banco relacional.

#### Alterado

- **Compatibilidade Obrigatória de Preço no Matcher**: Apenas o bairro compartilhado não gera mais oportunidades. É obrigatório que ambos os lados possuam preço e que a oferta esteja dentro da janela de preço válida: não pode exceder o orçamento do comprador **e** deve ser no mínimo 70% desse teto (`d.price * 0.70 <= o.price <= d.price`). Ofertas com preço mais de 30% abaixo do teto da demanda são descartadas para evitar matches irrelevantes.
- **Qualificação Estrita de Oportunidades no Engine**: Oportunidades de parceiros passam por validação de score mínimo (`score > 50`) diretamente no `intel-engine/engine.py`. Oportunidades com pontuação insuficiente são descartadas e logadas no Engine, mantendo o `wpp-egress` desacoplado e focado exclusivamente no disparo para o WhatsApp.
- **Super Prioridade para Inventário Majesto**: Imóveis próprios recebem +35 pontos de bônus no cálculo de score e são despachados diretamente na DM privada prioritária (`PRIORITY_CONTACT_ID`) **sem limite de envios por hora**. Matches de inventário ocorrem exclusivamente quando o imóvel está com status `DISPONIVEL` na tabela `public.imoveis`.
- **Sanitização de Tipos Numéricos**: Conversão de `decimal.Decimal` do PostgreSQL para `float` em todos os adaptadores para compatibilidade com o protocolo Bolt.

#### Corrigido

- **Flexibilização na Normalização de Preços sem Prefixo Monetário (`normalizer.py`)**:
  - O método `extract_price()` exigia a presença explícita do símbolo `R$`, falhando em mensagens como `"por 800k"`, `"até 800 mil"`, `"800k"`, `"1.8M"` e valores numéricos formatados (`800.000`).
  - Implementado extrator multi-padrão com suporte a prefixos operacionais (`valor`, `preco`, `ate`, `por`, `teto`, `orcamento`), multiplicadores (`k`, `mil`, `mi`, `m`, `milhão`, `milhões`) e milhares pontuados com piso mínimo de R$ 50.000,00.
- **Resolução de Bairros Pai para Condomínios e Correção de Máscara (`normalizer.py`)**:
  - O mascaramento anterior de condomínios (`XXXXXX`) apagava menções a condomínios isolados, deixando `neighborhood: []` e projetando demandas no bairro `"DESCONHECIDO"`, impedindo matches.
  - Nova estratégia resolve primeiro o condomínio para seu bairro pai canônico (ex: `"maayan"` -> `["BARRA OLIMPICA", "BARRA"]`, `"peninsula"` -> `["BARRA"]`, `"barra sunday"` -> `["RECREIO"]`), permitindo matching perfeito com imóveis do inventário.

- **Taxonomia Canônica de Bairros & Mapeamento de Aliases (`normalizer.py`, `inventory_sync.py`, `graphs/neo4j_client.py`)**: O normalizador de PLN mapeava pedidos de corretores do WhatsApp para aliases canônicos (`"Barra da Tijuca"` -> `"BARRA"`, `"Recreio dos Bandeirantes"` -> `"RECREIO"`, `"Barra Olímpica"` -> `"BARRA OLIMPICA"`), enquanto a projeção do inventário do PostgreSQL (`bairros.nome`) criava nós com a grafia literal (`"BARRA DA TIJUCA"`, `"RECREIO DOS BANDEIRANTES"`, `"BARRA OLÍMPICA"` com acento). Essa divergência taxonômica isolava 85% do inventário Majesto, impedindo qualquer cruzamento no grafo. Corrigido com a introdução de `canonical_neighborhood()` e `_normalize_neighborhood()` em todo o pipeline, além de unificação retroativa dos nós no Neo4j.
- **Extração de Características Semânticas da Coluna Descrição (`inventory_sync.py`)**: Anteriormente, `property_to_inventory_ad()` não extraía informações da coluna `descricao`, fixando `seafront=None`, `nearbeach=False` e `condominium=False`. Quando um corretor exigia frente mar (`d.seafront = true`), os imóveis da base eram sumariamente descartados. Agora, o `NormalizedAd` extrai frente mar ("frontal mar", "frente mar"), proximidade da praia, condomínio e posição solar normalizada diretamente de `public.imoveis.descricao`.
- **Relaxamento da Constraint em `opportunities.seller_message_id` (`migrations/004_relax_opportunity_seller_message_reference.sql`)**: Removida a FK `opportunities_seller_message_id_fkey` para `raw_messages`. Ofertas do inventário Majesto utilizam identificadores sintéticos (`self-<property_id>`) que não existem na tabela de mensagens do WhatsApp; a FK anterior disparava erro de `ForeignKeyViolation` ao salvar matches do inventário, travando o engine em loop de retry no RabbitMQ.
- **Vinculação Multi-Localidade de Imóveis no Grafo (`graphs/neo4j_client.py`)**: Nós `Imovel` agora associam-se a todas as localidades pertinentes (bairro canônico e sub-bairros/condomínios extraídos da descrição, ex: `CIDADE JARDIM` e `BARRA OLIMPICA`) via Cypher `FOREACH`, permitindo matching tanto em buscas amplas quanto específicas.
- **Normalização de Tipologia para MAIÚSCULAS no Grafo**: Padronização de `property_type` garantindo equivalência exata entre demandas e ofertas.

---

## [1.7.1] - 2026-07-17

### English

#### Fixed

- `wpp-collector/package.json` / `wpp-egress/package.json`: Updated `whatsapp-web.js` dependency to tracking fork (`github:lindionez/whatsapp-web.js#feat/fix-_serialized-id-fallback`). This handles the July 2026 WhatsApp Web infrastructure update that renamed internal message/contact serialized IDs from `_serialized` to `$1`, preventing immediate `TypeError` crashes across the collection and egress pipelines.

---

### Português

#### Corrigido

- `wpp-collector/package.json` / `wpp-egress/package.json`: Atualizada a dependência `whatsapp-web.js` para o fork de correção da comunidade (`github:lindionez/whatsapp-web.js#feat/fix-_serialized-id-fallback`). A alteração resolve o crash por `TypeError` causado pela mudança interna do WhatsApp Web (julho de 2026), que alterou a propriedade de IDs serializados de `_serialized` para `$1`, normalizando o pipeline de coleta e envio.

---

## [1.7.0] - 2026-07-08

### English

#### Added

- **New module `database.py`** (did not exist in any prior release): reads available properties from an external SQLite database and exposes `get_available_properties()` and `get_property_details()`. `get_property_details()` returns structured dicts (`message_id`, `message`, `author_name`, `author_phone`); `message_id` is a stable hash (`self-<md5>`) derived from the property description, so it survives engine restarts without depending on any specific database schema.
- **New feature: self-owned property prioritization**, built entirely on top of the new `database.py` module:
  - `normalizer.py`: `run_self_normalizer()` now attaches the property dict as `original_content`, making self-ads compatible with `matcher.py` and `egest.py`, which both require `original_content["message_id"]`.
  - `egest.py`: New `export_self_opportunities()`, writing to a dedicated `data/self_opportunities.jsonl` — kept fully separate from third-party opportunities (`opportunities.jsonl`).
  - `engine.py`: Now computes and exports `self_opportunities` — matches between `database.py` properties and current buyers — for the first time.
  - `wpp-egress/main.js`: New `dispatchSelfLoop()` sends self-opportunities as a **direct message** to `PRIORITY_CONTACT_ID`, with its own dispatch state (`sent_self` in `state.json`), independent from the group dispatch loop.
- `cleaner.py` / `purge_user.py`: Deduplication, expiration (15-day window), and blocked-user purge now cover `self_opportunities.jsonl` as well.
- `engine.py`: Cleanup routines from `cleaner.py` are now called automatically from the main loop on a time-based interval (`CLEANUP_INTERVAL_SECONDS`, default 1 hour) — no longer requires running `cleaner.py` manually.
- `ecosystem.config.js`: New pm2 configuration managing the three long-running processes (`sentinel-collector`, `sentinel-egress`, `sentinel-engine`), enabling 24/7 deployment with `pm2 startup`/`pm2 save`.

#### Changed

- `wpp-egress/main.js`: Regular (non-self) opportunity dispatch (`dispatchLoop()`) is temporarily disabled (commented out) for testing — only self-opportunity notifications are active for now.
- `engine.py`: Regular opportunity matching/export (`get_opportunity` + `export_opportunities` for third-party buyer/seller pairs) is commented out for the same reason. Self-opportunity matching remains fully active.

#### Fixed

- `wpp-collector/main.js`: `setTimeout(startBot(), 30000)` invoked `startBot()` immediately instead of scheduling a retry — fixed to `setTimeout(startBot, 30000)` (two occurrences).
- `wpp-collector/main.js`: `persistence.log(...)` referenced an undefined variable, throwing inside the reconnect `catch` block and crashing the process on the first connection failure instead of retrying. Replaced with `console.error`.
- `ecosystem.config.js`: `sentinel-engine` used a bare `"python3"` interpreter, which pm2's daemon resolves against its own `PATH` — not the interactive shell's. On machines using a virtualenv for `intel-engine`'s dependencies (spaCy + `pt_core_news_lg`), this could silently fall back to the system Python and fail to import them. Fixed by pointing `interpreter` directly at the venv's binary (`path.join(__dirname, "intel-engine", "venv", "bin", "python")`), removing the ambiguity entirely.

---

### Português

#### Adicionado

- **Novo módulo `database.py`** (não existia em nenhuma versão anterior): lê os imóveis disponíveis de um banco SQLite externo e expõe `get_available_properties()` e `get_property_details()`. `get_property_details()` retorna dicts estruturados (`message_id`, `message`, `author_name`, `author_phone`); o `message_id` é um hash estável (`self-<md5>`) derivado da descrição do imóvel, sobrevivendo a reinícios do engine sem depender do schema específico do banco.
- **Nova funcionalidade: priorização de imóveis próprios**, construída inteiramente sobre o novo módulo `database.py`:
  - `normalizer.py`: `run_self_normalizer()` agora anexa o dict do imóvel como `original_content`, tornando os anúncios próprios compatíveis com `matcher.py` e `egest.py`, que exigem `original_content["message_id"]`.
  - `egest.py`: Nova `export_self_opportunities()`, gravando em `data/self_opportunities.jsonl` dedicado — mantido totalmente separado das oportunidades de terceiros (`opportunities.jsonl`).
  - `engine.py`: Agora calcula e exporta `self_opportunities` — cruzamento entre os imóveis do `database.py` e os compradores atuais — pela primeira vez.
  - `wpp-egress/main.js`: Nova `dispatchSelfLoop()` envia oportunidades próprias como **mensagem direta** para `PRIORITY_CONTACT_ID`, com estado de dispatch próprio (`sent_self` em `state.json`), independente do loop de dispatch do grupo.
- `cleaner.py` / `purge_user.py`: Deduplicação, expiração (janela de 15 dias) e purge de usuário bloqueado agora cobrem `self_opportunities.jsonl` também.
- `engine.py`: As rotinas de limpeza do `cleaner.py` agora são chamadas automaticamente pelo loop principal, em intervalo de tempo (`CLEANUP_INTERVAL_SECONDS`, padrão 1 hora) — não exige mais rodar `cleaner.py` manualmente.
- `ecosystem.config.js`: Nova configuração pm2 gerenciando os três processos de longa duração (`sentinel-collector`, `sentinel-egress`, `sentinel-engine`), habilitando deploy 24/7 com `pm2 startup`/`pm2 save`.

#### Alterado

- `wpp-egress/main.js`: Dispatch de oportunidades regulares (não-próprias) (`dispatchLoop()`) foi temporariamente desativado (comentado) para testes — só notificações de oportunidades próprias estão ativas por enquanto.
- `engine.py`: Matching/export de oportunidades regulares (`get_opportunity` + `export_opportunities` para pares comprador/vendedor de terceiros) foi comentado pelo mesmo motivo. O matching de oportunidades próprias segue totalmente ativo.

#### Corrigido

- `wpp-collector/main.js`: `setTimeout(startBot(), 30000)` chamava `startBot()` imediatamente em vez de agendar o retry — corrigido para `setTimeout(startBot, 30000)` (duas ocorrências).
- `wpp-collector/main.js`: `persistence.log(...)` referenciava uma variável inexistente, lançando exceção dentro do `catch` de reconexão e derrubando o processo no primeiro erro de conexão em vez de tentar de novo. Substituído por `console.error`.
- `ecosystem.config.js`: `sentinel-engine` usava o interpreter `"python3"` puro, que o daemon do pm2 resolve pelo próprio `PATH` — não pelo do shell interativo. Em máquinas com virtualenv para as dependências do `intel-engine` (spaCy + `pt_core_news_lg`), isso podia cair silenciosamente no Python do sistema e falhar ao importar essas libs. Corrigido apontando o `interpreter` direto pro binário da venv (`path.join(__dirname, "intel-engine", "venv", "bin", "python")`), eliminando a ambiguidade.

---

## [1.6.2] - 2026-03-27

### English

- **Fixed**: Race condition in `engine.py` by ensuring `save_state()` is called before `export_opportunities()`. This prevents duplicate opportunities if the engine crashes.

---

### Português

- **Corrigido**: Condição de corrida no `engine.py` garantindo que o `save_state()` seja chamado antes do `export_opportunities()`. Isso evita duplicatas caso a engine caia durante a execução.

## [1.6.1] - 2026-03-24

### English

#### Fixed

- `cleaner.py`: Replaced `dedup_engine_state()` with `reconcile_engine_state()` — instead of just removing duplicates, the function now rebuilds `seen_ids` and `seen_hashes` from scratch based on the current `messages.jsonl`, keeping `engine_state.json` strictly proportional to the messages file and preventing unbounded growth.

- `cleaner.py`: Replaced manual accent substitution table in `_normalize_for_hash` with `unicodedata.normalize("NFD")` — now exhaustively covers all Unicode characters, guaranteeing hash parity with `main.js` for any input.

### Português

#### Corrigido

- `cleaner.py`: Substituída `dedup_engine_state()` por `reconcile_engine_state()` — em vez de apenas remover duplicatas, a função agora reconstrói `seen_ids` e `seen_hashes` do zero a partir do `messages.jsonl` atual, mantendo o `engine_state.json` estritamente proporcional ao arquivo de mensagens e prevenindo crescimento ilimitado.

- `cleaner.py`: Substituída tabela manual de acentos em `_normalize_for_hash` por `unicodedata.normalize("NFD")` — agora cobre exaustivamente todos os caracteres Unicode, garantindo paridade de hash com o `main.js` para qualquer entrada.

## [1.6.0] - 2026-03-24

### English

#### Added

- `cleaner.py`: Full deduplication pipeline — messages deduplicated by `message_id` and `ad_hash`, with on-the-fly hash recomputation for legacy records missing the field.
- `cleaner.py`: New `dedup_engine_state()` — removes duplicate `seen_ids` and `seen_hashes` from `engine_state.json`, which previously grew unbounded.
- `cleaner.py`: New `dedup_dispatch_state()` — sanitizes `state.json` by removing null/invalid entries from the `sent` dict.
- `egest.py`: Pre-write dedup check — `export_opportunities` now reads existing IDs before appending, preventing duplicate opportunity pairs across engine restarts.
- `engine.py`: Intra-batch dedup via `batch_ids` and `batch_hashes` — blocks duplicate messages that arrive in the same processing cycle before `save_state` runs.

#### Changed

- `cleaner.py`: `clean_old_messages`, `clean_old_opportunities`, and `clean_old_buyers` merged into unified functions `clean_and_dedup_messages()` and `clean_and_dedup_opportunities()`.
- `cleaner.py`: Opportunity retention window reduced from **30 days to 15 days**.

### Português

#### Adicionado

- `cleaner.py`: Pipeline completo de deduplicação — mensagens deduplicadas por `message_id` e `ad_hash`, com recálculo de hash em tempo de execução para registros antigos sem o campo.
- `cleaner.py`: Nova função `dedup_engine_state()` — remove `seen_ids` e `seen_hashes` duplicados do `engine_state.json`, que antes crescia indefinidamente.
- `cleaner.py`: Nova função `dedup_dispatch_state()` — sanitiza o `state.json` removendo entradas nulas/inválidas do dict `sent`.
- `egest.py`: Verificação de dedup antes do append — `export_opportunities` agora lê os IDs existentes antes de gravar, prevenindo pares de oportunidades duplicados entre reinicializações do engine.
- `engine.py`: Dedup intra-batch via `batch_ids` e `batch_hashes` — bloqueia mensagens duplicadas que chegam no mesmo ciclo de processamento, antes do `save_state` executar.

#### Alterado

- `cleaner.py`: As funções `clean_old_messages`, `clean_old_opportunities` e `clean_old_buyers` foram unificadas em `clean_and_dedup_messages()` e `clean_and_dedup_opportunities()`.
- `cleaner.py`: Janela de retenção de oportunidades reduzida de **30 para 15 dias**.

## [1.5.0] - 2026-03-24

### English

#### Added

- Added **Saint Tropez** to the recognized condominiums list in the normalizer.
- New `generateHash` logic using regex to strip emojis, symbols, and extra spaces for better deduplication.

#### Changed

- Updated **Cidade Jardim** location mapping: now linked to **Barra Olímpica** instead of Barra da Tijuca.
- Upgraded `whatsapp-web.js` dependency to the latest version for improved stability.

---

### Português

#### Adicionado

- Adicionado o condomínio **Saint Tropez** à lista de condomínios reconhecidos no normalizador.
- Nova lógica de `generateHash` usando regex para remover emojis, símbolos e espaços extras, melhorando a deduplicação.

#### Alterado

- Atualizado o mapeamento do bairro **Cidade Jardim**: agora vinculado à **Barra Olímpica** em vez da Barra da Tijuca.
- Atualizada a dependência `whatsapp-web.js` para a versão mais recente visando maior estabilidade.

## [1.4.0] - 2026-03-24

### Added (Inglês)

- Support for `sub_neighborhood` extraction using spaCy in `normalizer.py`.
- Exact match logic for sub-localities in `matcher.py`.

### Adicionado (Português)

- Suporte para extração de `sub_neighborhood` usando spaCy no `normalizer.py`.
- Lógica de correspondência exata para sub-localidades no `matcher.py`.

### Changed (Inglês)

- `formatNeighborhood` in `main.js` now supports dual-level location display.
- Seller deduplication now prioritizes sub-neighborhoods over string length.

### Alterado (Português)

- `formatNeighborhood` no `main.js` agora suporta exibição de localização em dois níveis.
- A deduplicação de vendedores agora prioriza sub-bairros em vez do comprimento da string.

## [1.3.0] - 2026-02-11 (EN)

### Added

- Intelligent Matching Engine: Scoring system to pair buyer profiles with seller offers based on extracted features.
- Advanced OOP in Python: Implementation of Properties, Abstract Classes, and Iterators for a robust backend.
- Business Logic: 3-month window restriction to prevent duplicate property ads from the same broker.

### Changed

- Improved pipeline architecture between Node.js (collection) and Python (processing).

## [1.2.0] - 2026-01-25 (EN)

### Added

- NLP Integration: Added **spaCy** for message normalization and entity classification (Property types, values, and locations).
- Regex-based pre-processing for noise reduction in raw WhatsApp messages.

## [1.1.0] - 2026-01-10 (EN)

### Added

- Persistence layer: Initial implementation of data storage for collected opportunities.
- Real-time message ingestion via `whatsapp-web.js` (Node.js).

## [1.0.0] - 2026-01-02 (EN)

### Added

- Initial project release.
- Connection module with WhatsApp Web and basic message monitoring.

---

## [1.3.0] - 2026-02-11 (PT)

### Adicionado

- Mecanismo de Matching Inteligente: Sistema de scoring para casar perfis de compradores com ofertas de vendedores baseando-se em características extraídas.
- POO Avançada em Python: Implementação de Properties, Classes Abstratas e Iteradores para um backend robusto.
- Regra de Negócio: Restrição de janela de 3 meses para evitar anúncios duplicados do mesmo corretor.

### Alterado

- Melhoria na arquitetura do pipeline entre Node.js (coleta) e Python (processamento).

## [1.2.0] - 2026-01-25 (PT)

### Adicionado

- Integração de PLN: Adicionado **spaCy** para normalização de mensagens e classificação de entidades (Tipos de imóveis, valores e localizações).
- Pré-processamento via Regex para redução de ruído em mensagens brutas do WhatsApp.

## [1.1.0] - 2026-01-10 (PT)

### Adicionado

- Camada de persistência: Implementação inicial de armazenamento de dados para oportunidades coletadas.
- Ingestão de mensagens em tempo real via `whatsapp-web.js` (Node.js).

## [1.0.0] - 2026-01-02 (PT)

### Adicionado

- Lançamento inicial do projeto.
- Módulo de conexão com WhatsApp Web e monitoramento básico de mensagens.
