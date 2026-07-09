# Changelog - Sentinel Bot

All notable changes to this project will be documented in this file.
Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
