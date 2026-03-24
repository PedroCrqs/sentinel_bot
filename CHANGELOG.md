# Changelog - Sentinel Bot

All notable changes to this project will be documented in this file.
Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

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
