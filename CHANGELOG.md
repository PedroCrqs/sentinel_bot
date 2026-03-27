# Changelog - Sentinel Bot

All notable changes to this project will be documented in this file.
Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
