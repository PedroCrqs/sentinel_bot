# 🤖 Sentinel Bot

> Bot de inteligência imobiliária com arquitetura orientada a eventos (EDA) via **RabbitMQ**, persistência relacional em **PostgreSQL**, grafo de conhecimento em **Neo4j** e processamento de linguagem natural (NLP) via **spaCy**. Monitora grupos de WhatsApp, extrai intenções imobiliárias, projeta entidades em grafo e gera conexões semânticas em tempo real.

---

## 🏗️ Arquitetura do Sistema

O Sentinel Bot é composto por **4 serviços desacoplados**, orquestrados pelo **PM2** e comunicando-se via mensageria assíncrona:

```
[ WhatsApp ]
     │
     ▼
┌──────────────────┐
│  wpp-collector   │ ──(1. INSERT raw_messages)──> [ PostgreSQL ]
│     (Node.js)    │ ──(2. publish message_id)───> [ RabbitMQ (raw_messages) ]
└──────────────────┘                                      │
                                                          ▼
┌──────────────────┐                              ┌──────────────────┐
│  sentinel-engine │ <─────────────────────────── │  intel-engine    │
│     (Python)     │ ──(NLP: spaCy pt_core_lg)    │     (Python)     │
│                  │ ──(Projeta Demanda/Oferta)─> [ Neo4j Graph DB ] │
│                  │ ──(Match Cypher)───────────>         │          │
│                  │ ──(INSERT opportunities)───> [ PostgreSQL ]     │
│                  │ ──(publish opportunity_id)─> [ RabbitMQ (opps) ]│
└──────────────────┘                                      │
                                                          ▼
┌──────────────────┐                              ┌──────────────────┐
│    wpp-egress    │ <─────────────────────────── │  opportunities   │
│     (Node.js)    │ ──(Disparo WhatsApp DM/Grupo)                         │
└──────────────────┘
```

### Serviço Adicional: Worker de Sincronização de Inventário
- **`sentinel-inventory-sync`** (`inventory_sync_worker.py`): Worker independente que monitora o inventário de imóveis próprios (`public.imoveis`) no PostgreSQL, calcula fingerprints por hash SHA-256 e sincroniza snapshots/diffs diretamente no Neo4j com suporte a status ativos/inativos sem apagar histórico.

---

## 🗄️ Infraestrutura e Bancos de Dados

### 1. PostgreSQL (Docker `postgres:16-alpine`)
- **`raw_messages`**: Fila de mensagens recebidas (`message_id`, `author_id`, `author_name`, `message`, `ad_hash`, `timestamp`, `status`, `normalized_data`).
- **`opportunities`**: Oportunidades geradas pelo matcher (`opportunity_id`, `buyer_message_id`, `seller_message_id`, `matched_imovel_id`, `match_score`, `match_details`, `dispatch_status`, `rule_version`).
- **`inventory_sync_state`**: Tabela de controle de versão dos imóveis sincronizados (`property_id`, `fingerprint`, `source_status`, `is_present`, `last_synced_at`).
- **`imoveis`**: Tabela do sistema imobiliário com inventário próprio da Majesto.

### 2. RabbitMQ (Docker `rabbitmq:3-management`)
- Porta `5672` (AMQP) e `15672` (Management Dashboard).
- Fila `raw_messages`: Notificação instantânea para o engine a cada nova mensagem ingerida.
- Fila `opportunities_queue`: Notificação instantânea para o egress a cada oportunidade qualificada.
- QOS configurado (`prefetch_count=1`) para controle estrito de fluxo e concorrência justa.

### 3. Neo4j Graph Database (Docker `neo4j:5.26.0-community`)
- Portas `7687` (Bolt) e `7474` (HTTP Browser).
- Arquitetura de Grafo:
  ```
  (Pessoa)-[:CRIOU]->(Demanda)-[:BUSCA_EM]->(Bairro)
  (Pessoa)-[:PUBLICOU]->(Oferta)-[:REFERE_SE_A]->(Imovel)-[:LOCALIZADO_EM]->(Bairro)
  (Mensagem)-[:EXPRESSA]->(Demanda)
  (Mensagem)-[:ORIGINA]->(Oferta)
  ```
- Constraints de unicidade aplicadas em `Pessoa.person_id`, `Mensagem.id`, `Demanda.demand_id`, `Oferta.offer_id`, `Imovel.id`.

---

## 🎯 Regras de Negócio, Matching e Scoring

### 1. Critérios de Compatibilidade (Cypher Match)
- **Localização e Bairro**: O comprador e o imóvel devem compartilhar ao menos um bairro de interesse.
- **Preço Obrigatório**: **É imprescindível que o preço bata**. Ambos os lados devem informar preço e `Oferta.price <= Demanda.price`. Mensagens sem preço ou fora do teto não geram oportunidade.
- **Tipologia e Quartos**: Quartos devem atender ao mínimo da demanda (`Imovel.quartos >= Demanda.bedrooms`), caso informado.
- **Frente Mar**: Se o comprador exigir frente mar, o imóvel obrigatoriamente deve possuir frente mar.

### 2. Tabela de Pontuação (Score)
| Critério | Pontuação | Descrição |
|---|---|---|
| **Base + Bairro** | **15 pts** | Localização compatível entre demanda e oferta |
| **Preço Válido** | **20 pts** | Preço dentro do teto estipulado pelo comprador |
| **Inventário Majesto** | **+35 pts** | **Super prioridade** para imóveis próprios da base |
| **Quartos** | **15 pts** | Quantidade de quartos compatível |
| **Tipologia** | **10 pts** | Tipo de imóvel (Apartamento, Casa, Cobertura, etc.) |
| **Área** | **10 pts** | Metragem privativa compatível |
| **Frente Mar** | **10 pts** | Imóvel frente mar atendendo à exigência |
| **Vagas de Garagem** | **5 pts** | Quantidade de vagas atendida |
| **Condomínio** | **5 pts** | Condomínio fechado |
| **Posição Solar** | **5 pts** | Sol da manhã / passante |
| **Próximo à Praia** | **5 pts** | Imóvel perto da praia |

### 3. Filtros do Egress (WhatsApp)
- **Score Mínimo**: Apenas oportunidades com **`score > 50`** são disparadas pelo `wpp-egress`. Oportunidades com pontuação inferior são descartadas para evitar ruído.
- **Inventário Majesto (DM Prioritária)**: Matches com imóveis próprios vão diretamente para o contato privado (`PRIORITY_CONTACT_ID`) **sem limite de envios por hora**.
- **Parcerias / Terceiros (Grupo)**: Matches entre corretores parceiros vão para o grupo (`GROUP_ID`) com limitador de vazão de segurança (`MAX_GROUP_OPPS_PER_HOUR`, padrão 10 envios/hora).

---

## 🧹 Política de Retenção e Faxina (Cleaner)

O módulo `cleaner.py` roda de forma contínua e automatizada via daemon em segundo plano no `sentinel-engine` (a cada 6 horas):
- **Ofertas de Terceiros**: Mantidas por no máximo **90 dias** (removidas do Neo4j e PostgreSQL).
- **Demandas de Compradores**: Mantidas por no máximo **15 dias** (removidas do Neo4j e PostgreSQL).
- **Inventário Majesto**: **Nunca é expurgado por tempo**, sendo gerenciado exclusivamente pelo `inventory_sync_worker`.
- **Nós Órfãos**: Limpeza em cascata de nós `Imovel` de terceiros sem ofertas ativas e nós `Pessoa` sem ofertas ou demandas vinculadas.

---

## ⚙️ Variáveis de Ambiente (`.env`)

Crie o arquivo `.env` na raiz do projeto com base no `.env.example`:

```env
# PostgreSQL
DATABASE_URL=postgresql://imoveis_app:SUA_SENHA@localhost:5432/imoveis
POSTGRES_USER=imoveis_app
POSTGRES_PASSWORD=SUA_SENHA
POSTGRES_DB=imoveis

# RabbitMQ
RABBITMQ_URL=amqp://localhost:5672

# Neo4j Local (Docker)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=SUA_SENHA_NEO4J

# Filtros WhatsApp
BLOCKED_IDS=id1@lid,id2@lid

# Destinatários WhatsApp (Egress)
GROUP_ID=120363424642701935@g.us
PRIORITY_CONTACT_ID=96654279573661@lid
```

---

## 🚀 Instalação e Execução

### 1. Subir Infraestrutura Docker

```bash
# Subir o Neo4j local persistente
docker compose -f docker-compose.neo4j.yml up -d

# Aplicar constraints iniciais no Neo4j
docker cp infra/neo4j/constraints.cypher sentinel-neo4j:/tmp/constraints.cypher
docker exec sentinel-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -f /tmp/constraints.cypher
```

### 2. Configurar o Python (`intel-engine`)

```bash
cd intel-engine
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar os Módulos Node.js

```bash
cd ../wpp-collector && npm install
cd ../wpp-egress && npm install
```

### 4. Executar Migrações do Banco

```bash
cd ../intel-engine
source .venv/bin/activate
python -c "
from database import get_db_connection
from pathlib import Path
conn = get_db_connection()
cur = conn.cursor()
for m in ['../migrations/001_align_opportunities_contract.sql', '../migrations/002_add_inventory_sync_state.sql', '../migrations/003_relax_opportunity_property_reference.sql']:
    cur.execute(Path(m).read_text(encoding='utf-8'))
conn.commit()
conn.close()
"
```

### 5. Iniciar com PM2

```bash
cd ..
pm2 start ecosystem.config.js
pm2 save
```

Processos gerenciados pelo PM2:
1. `sentinel-collector`: Escuta WhatsApp e publica em `raw_messages`.
2. `sentinel-engine`: Consome mensagens, classifica com spaCy e projeta no Neo4j.
3. `sentinel-egress`: Consome `opportunities_queue` e envia notificações via WhatsApp.
4. `sentinel-inventory-sync`: Sincroniza periodicamente o inventário de imóveis no Neo4j.

---

## 🧪 Suíte de Testes

Execute a suíte completa de testes unitários:

```bash
cd intel-engine
source .venv/bin/activate
python -m unittest discover -s tests
```

Executar teste de integração com o Neo4j ativo:

```bash
RUN_NEO4J_INTEGRATION=1 python tests/test_neo4j_integration.py
```

---

## 📊 Dashboard de Matches (Streamlit)

O projeto inclui interface Streamlit para visualização em tempo real das conexões geradas no grafo:

```bash
streamlit run app.py
```
