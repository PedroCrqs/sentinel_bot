# 🤖 Sentinel Bot

> Bot de monitoramento e detecção inteligente de oportunidades imobiliárias via WhatsApp, com matching semântico, normalização e classificação automática.

---

## ✨ Funcionalidades

- Coleta de mensagens do WhatsApp em tempo real, com deduplicação e blocklist na origem (`wpp-collector`)
- Classificação automática de mensagens (venda, compra, inútil)
- Normalização e extração de atributos (bairro, preço, quartos, condomínio, etc.) via spaCy
- Matching semântico entre compradores e vendedores (`intel-engine`)
- **Priorização de imóveis próprios**: imóveis cadastrados no seu banco (`database.py`) são cruzados com compradores e notificados por **DM direta**, separado do fluxo normal
- Disparo de notificações via WhatsApp, isolado em seu próprio processo (`wpp-egress`)
- Limpeza automática de dados (deduplicação, expiração por idade) integrada ao ciclo do engine
- Purge de usuário bloqueado (`purge_user.py`)
- Deploy 24/7 via `pm2`, três processos independentes

> ⚠️ **Status atual (v1.7.0):** o dispatch de oportunidades **regulares** (comprador × vendedor externo) está em *standby* para fins de teste. Só as oportunidades envolvendo imóveis próprios notificam no momento. Ver [CHANGELOG](CHANGELOG.md).

---

## 🏗️ Arquitetura

O projeto é dividido em **três módulos independentes**, cada um seu próprio processo, cada um sua própria pasta com `package.json`/dependências próprias:

```
wpp-collector  →  data/messages.jsonl  →  intel-engine  →  data/*_opportunities.jsonl  →  wpp-egress
   (Node)                                    (Python)                                        (Node)
```

- **`wpp-collector`** — conecta no WhatsApp, escuta um grupo, grava cada mensagem nova em `data/messages.jsonl`. Só ingest: não sabe nada sobre matching ou notificações.
- **`intel-engine`** — lê `data/messages.jsonl`, classifica, normaliza, faz o matching (comprador × vendedor e comprador × imóvel próprio), exporta as oportunidades e roda a limpeza periódica dos dados.
- **`wpp-egress`** — conecta no WhatsApp (sessão própria, pode ser um número diferente do `wpp-collector`), lê os arquivos de oportunidades e envia as notificações — pro grupo ou por DM.

Por serem pastas/pacotes Node separados, cada módulo já tem sua própria sessão de autenticação (`session/` dentro da respectiva pasta) — não há risco de um processo derrubar a sessão do outro, mesmo usando números de WhatsApp diferentes.

---

## 🛠️ Requisitos

- Python 3.13 com [spaCy](https://spacy.io/) e o modelo `pt_core_news_lg`
- Node.js 18+ (para `whatsapp-web.js`, em `wpp-collector` e `wpp-egress`)
- [pm2](https://pm2.keymetrics.io/) instalado globalmente (`npm install -g pm2`)
- Um banco SQLite de imóveis próprios acessível pelo `intel-engine/database.py` (ver seção [Banco de imóveis próprios](#-banco-de-imóveis-próprios-databasepy))

> ⚠️ **Importante:** o `ecosystem.config.js` aponta o `sentinel-engine` direto para `intel-engine/venv/bin/python`. O pm2 roda como daemon e resolve `"python3"` pelo próprio `PATH`, não pelo do seu shell — então a venv **precisa** estar nesse caminho exato (`intel-engine/venv`), ou o `sentinel-engine` sobe usando o Python errado (sem spaCy instalado) e fica em crash-loop.

---

## 📦 Instalação

```bash
# Clone o repositório
git clone https://github.com/PedroCrqs/sentinel_bot.git
cd sentinel_bot

# intel-engine (Python)
cd intel-engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download pt_core_news_lg
deactivate
cd ..

# wpp-collector (Node) — dependências próprias
cd wpp-collector
npm install
cd ..

# wpp-egress (Node) — dependências próprias
cd wpp-egress
npm install
cd ..

# pm2 (se ainda não tiver)
npm install -g pm2
```

---

## ▶️ Como usar

Os três processos são gerenciados via `pm2`, a partir do `ecosystem.config.js` na raiz do projeto:

```bash
pm2 start ecosystem.config.js
pm2 logs          # acompanhar os três processos
pm2 status         # ver se estão rodando
```

Na primeira execução do `sentinel-collector` e do `sentinel-egress`, escaneie o QR Code exibido no terminal (`pm2 logs sentinel-collector` / `pm2 logs sentinel-egress`) pra autenticar cada sessão do WhatsApp Web. Se usar números diferentes para coletar e para notificar, escaneie com o celular correspondente a cada um.

Veja [Deploy 24/7 com pm2](#-deploy-247-com-pm2) para deixar isso rodando permanentemente na máquina.

---

## 🏠 Banco de imóveis próprios (`database.py`)

Imóveis com `ImovelStatus = 'Disponível'` são lidos de um banco SQLite externo e cruzados contra os compradores identificados no WhatsApp. Quando há match, você recebe uma **DM direta** (não vai pro grupo) — essa é a via prioritária.

Pontos importantes:

- `intel-engine/database.py` espera o banco em `../../imoveis-database/data/imoveis.db` (fora da pasta `sentinel_bot/`, como projeto irmão). Ajuste `DB_PATH` em `database.py` se sua estrutura for diferente.
- Cada imóvel vira um `message_id` estável (`self-<hash da descrição>`), calculado a partir do texto da coluna `Descricao`. Se a descrição do imóvel mudar, ele é tratado como um "novo anúncio" — isso é intencional.
- As oportunidades geradas por esse cruzamento vão para `data/self_opportunities.jsonl`, separado de `data/opportunities.jsonl` (oportunidades entre terceiros). Isso mantém os dois fluxos independentes: dedup, expiração (15 dias) e dispatch cada um com seu próprio estado.
- No `wpp-egress/main.js`, o destino da DM é fixado em `PRIORITY_CONTACT_ID`. Atualize esse valor com o seu ID de contato no formato usado pelo `whatsapp-web.js` (`@c.us` ou `@lid`, dependendo do seu número).

---

## 🚫 Bloqueio de usuários — duas camadas diferentes

O projeto tem dois mecanismos de bloqueio, com propósitos distintos — não confundir um com o outro:

| Mecanismo                          | Onde                           | Quando age                                     | Efeito                                                                                                 |
| ---------------------------------- | ------------------------------ | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `BLOCKED_IDS`                    | `wpp-collector/main.js`      | No momento da captura                          | Mensagens do usuário nunca chegam a ser gravadas em`messages.jsonl`                                 |
| `BLOCKED_ID` + `purge_user.py` | `intel-engine/purge_user.py` | Sob demanda, manual (`python purge_user.py`) | Remove retroativamente tudo que já foi gravado (mensagens e oportunidades) de um usuário específico |

Se quer impedir a captura de um usuário dali pra frente, adicione o ID em `BLOCKED_IDS` (`wpp-collector/main.js`) e reinicie o `sentinel-collector`. Se quer apagar o que já foi coletado dele, rode `purge_user.py` com o ID em `BLOCKED_ID`.

---

## 🧹 Limpeza automática (`cleaner.py`)

Antes só rodava manualmente (`python cleaner.py`). Agora o `intel-engine/engine.py` chama as rotinas de limpeza sozinho, a cada **1 hora** (`CLEANUP_INTERVAL_SECONDS`, dentro de `engine.py`):

- `clean_and_dedup_messages()` — remove mensagens expiradas (3 meses) e compradores antigos (30 dias), dedup por `message_id`/`ad_hash`
- `clean_and_dedup_opportunities()` — remove oportunidades regulares expiradas (15 dias) e duplicadas
- `clean_and_dedup_self_opportunities()` — mesma coisa, para `self_opportunities.jsonl`
- `reconcile_engine_state()` — reconstrói `engine_state.json` a partir do `messages.jsonl` atual
- `dedup_dispatch_state()` — remove entradas inválidas de `state.json`

Você ainda pode rodar `python cleaner.py` manualmente a qualquer momento — o script continua funcionando isoladamente, o `engine.py` só automatizou a chamada periódica.

---

## 🚀 Deploy 24/7 com pm2

O `ecosystem.config.js` na raiz do projeto define os três processos, cada um com o `cwd` apontando pra sua pasta:

```bash
# 1. Iniciar os processos
pm2 start ecosystem.config.js

# 2. Persistir a lista de processos atual
pm2 save

# 3. Gerar o script de boot (roda uma vez, copie e execute o comando que ele imprimir)
pm2 startup

# A partir daqui, os processos sobem sozinhos após reboot da máquina.
```

Comandos úteis no dia a dia:

```bash
pm2 status                     # visão geral dos processos
pm2 logs sentinel-engine       # logs só do engine
pm2 logs sentinel-collector    # logs só da coleta
pm2 restart sentinel-egress    # reiniciar (ex: após trocar PRIORITY_CONTACT_ID)
pm2 stop ecosystem.config.js   # parar tudo
```

`autorestart: true` no `ecosystem.config.js` garante que, se qualquer processo cair, o pm2 sobe de novo automaticamente — cada um de forma independente, sem afetar os outros dois.

---

## 🗂️ Estrutura do Projeto

```
sentinel_bot/
├── data/                          # Dados e estado, compartilhados pelos 3 módulos (ignorados pelo git)
│   ├── messages.jsonl
│   ├── opportunities.jsonl        # oportunidades regulares (standby, ver CHANGELOG)
│   ├── self_opportunities.jsonl   # oportunidades de imóveis próprios (prioritárias)
│   ├── engine_state.json
│   └── state.json
├── intel-engine/                  # classificação, normalização, matching, cleanup (Python)
│   ├── classifier.py
│   ├── normalizer.py
│   ├── matcher.py
│   ├── database.py
│   ├── egest.py
│   ├── engine.py
│   ├── cleaner.py
│   ├── purge_user.py
│   └── requirements.txt
├── wpp-collector/                 # ingest: escuta o WhatsApp, grava messages.jsonl (Node)
│   ├── main.js
│   ├── package.json
│   └── package-lock.json
├── wpp-egress/                    # egest: envia as notificações via WhatsApp (Node)
│   ├── main.js
│   ├── package.json
│   └── package-lock.json
├── ecosystem.config.js            # configuração pm2 (os 3 processos)
├── CHANGELOG.md
├── LICENSE
└── readme.md
```

---

## 📋 Versões

Veja o [CHANGELOG](CHANGELOG.md) para o histórico completo de versões.

| Versão | Destaque                                                                                                                         |
| ------- | -------------------------------------------------------------------------------------------------------------------------------- |
| v1.7.0  | Priorização de imóveis próprios (`database.py`), cleaner integrado ao engine, deploy via pm2 com 3 processos independentes |
| v1.6.2  | Correção de race condition no engine                                                                                           |
| v1.6.0  | Pipeline de deduplicação completo                                                                                              |
| v1.3.0  | Zone matching, sun_type, seafront e normalização                                                                               |
| v1.2.0  | Dados e estrutura de cleaner                                                                                                     |
| v1.1.0  | Matcher aprimorado                                                                                                               |
| v1.0.0  | Primeiro release estável                                                                                                        |

---

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
