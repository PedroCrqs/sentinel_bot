# Contrato de mudanças do inventário

Status: contrato formalizado em 2026-08-31. Esta documentação não autoriza
alterações no banco imobiliário.

## Ownership e source of truth

`public.imoveis` e `public.bairros` são tratados pelo Sentinel como um
contrato de inventário externo/shared. O Sentinel é consumidor e não altera
tabelas, triggers ou funções desse schema sem autorização explícita do
proprietário do sistema imobiliário.

O source of truth é:

```text
PostgreSQL public.imoveis → estado do inventário
Neo4j                    → projeção derivada para matching
```

## Estado confirmado

`public.auditoria_imoveis` possui `logid` inteiro, PK e sequence. O banco real
possui os triggers `log_imovel_insert` e `log_imovel_update_status`.

Cobertura observada:

| Evento | Cobertura atual |
|---|---|
| Criação | `INSERT` |
| Alteração de status | `UPDATE` de `imovelstatus` |
| Alteração de preço | não registrada |
| Alteração de bairro | não registrada |
| Alteração de quartos/vagas | não registrada |
| Alteração de tipologia/metragem/sol/descrição | não registrada |
| Remoção física | não registrada |

Consequentemente, a tabela é um feed **PARCIAL** e não pode ser usada sozinha
para afirmar que o Neo4j está sincronizado.

## Campos relevantes

Os campos que afetam a projeção ou o matching são:

```text
imovelid       → identidade e vínculo da projeção
imovelstatus   → ciclo de vida da Oferta
valor          → preço da Oferta
bairroid       → localização do Imovel
quartos        → hard constraint de quartos
vagas          → ranking/preferência
tipologia      → tipo do Imovel
metragem       → ranking/preferência
sol            → ranking/preferência
descricao      → payload textual da oferta própria
```

`datacadastro` descreve criação, mas não é cursor de alteração. `datavenda`
descreve venda, mas não substitui auditoria geral. `caminhodrive` e
`linkpublico` não fazem parte do contrato canônico atual.

## Cursor

Quando o feed for ampliado, o cursor será:

```text
auditoria_imoveis.logid
```

Leitura:

```sql
WHERE logid > :last_cursor
ORDER BY logid ASC
```

Gaps de sequence são aceitáveis. O consumidor não deve calcular o próximo
cursor como `last_cursor + 1`.

## Contrato desejado do feed

O feed completo deverá permitir identificar:

```text
PROPERTY_CREATED
PROPERTY_UPDATED
PROPERTY_STATUS_CHANGED
PROPERTY_REMOVED
```

Os valores físicos atuais `INSERT`, `UPDATE` e `DELETE` podem ser mantidos se
`imovelid`, `logid`, `colunaalterada`, `valorantigo` e `valornovo` forem
suficientes para interpretar o evento.

O formato atual de uma linha por coluna alterada é suficiente e exige menos
mudança do que redesenhar a tabela. Updates relevantes devem usar
`IS DISTINCT FROM`, inclusive para transições envolvendo `NULL`, e não devem
gerar eventos quando o valor real não mudou.

## Status e Oferta

| Status externo | Status canônico | Oferta Neo4j |
|---|---|---|
| `Disponível` | `available` | `ACTIVE` |
| `Vendido` | `unavailable` | `INACTIVE` |
| `Alugado` | `unavailable` | `INACTIVE` |
| `Retirado de Venda` | `unavailable` | `INACTIVE` |

Estados externos não documentados não devem ser assumidos como ativos.

O adapter reconhece os quatro estados permitidos pela constraint atual. O
código de projeção ainda força ofertas de inventário para `ACTIVE`; essa
correção pertence à implementação do sync/lifecycle, não a esta formalização.

## DELETE

Não foram encontrados triggers ou código local que comprovem DELETE físico.
A classificação atual é `INDEFINIDO`.

Se o domínio usar somente remoção lógica por status, o sync tratará estados
indisponíveis como `Oferta.INACTIVE`. Se DELETE físico for autorizado e fizer
parte do contrato externo, ele deverá gerar evento `DELETE`; o Sentinel deverá
desativar a Oferta e preservar o nó `Imovel` histórico, sem exclusão automática.

## Atomicidade e replay

Triggers PostgreSQL normais executam na mesma transação da alteração que
registram. Para os eventos cobertos, alteração e auditoria são atômicas.

O futuro consumidor deverá:

```text
ler lote por logid
→ agrupar por imovelid
→ consultar estado atual em public.imoveis
→ projetar no Neo4j
→ avançar checkpoint somente após sucesso
```

Eventos repetidos do mesmo imóvel podem ser consolidados no estado final,
porque o PostgreSQL é a fonte oficial. Reprocessamento deve ser idempotente
por `imovelid`/`Oferta.offer_id`.

## Fallback enquanto o feed permanecer parcial

Não é seguro usar `auditoria_imoveis.logid` como único mecanismo incremental.
Até existir autorização e cobertura completa, a estratégia segura é:

```text
full snapshot + snapshot/diff periódico
```

O estado do diff deve ser Sentinel-owned e conter somente campos relevantes,
por exemplo `property_id`, fingerprint, status e `last_seen`.

## Implementação snapshot/diff

O estado Sentinel-owned é mantido em `inventory_sync_state`. O checkpoint
lógico é a combinação de `property_id`, `fingerprint`, `source_status`,
`is_present` e `last_synced_at`; não existe cursor artificial baseado em
`auditoria_imoveis.logid`.

O comando manual é:

```text
python inventory_sync.py sync
python inventory_sync.py full-rebuild
```

O snapshot lê todos os status de `public.imoveis`. Apenas propriedades
`NEW`, `CHANGED` e `REAPPEARED` são reprojetadas. Propriedades `UNCHANGED` não
são enviadas ao Neo4j. Ausências são marcadas `MISSING` somente após a leitura
completa do snapshot e desativam a Oferta sem apagar o Imóvel.

O modo `full-rebuild` força a reprojeção dos imóveis presentes, útil quando o
Neo4j foi recriado embora o estado Sentinel ainda exista.

Falha no PostgreSQL aborta o ciclo antes da classificação de ausências. Falha
no Neo4j impede a atualização do estado correspondente. Como não há transação
distribuída, a consistência é `at-least-once projection` com `MERGE`/`SET`
idempotente e replay seguro.

## Decisão de implementação

Não criar worker, scheduler, RabbitMQ inventory events ou triggers nesta
tarefa. O agendamento periódico permanece separado; o sincronizador atual é
 callable e manual. A execução periódica é feita pelo processo dedicado
 `inventory_sync_worker.py`, gerenciado pelo PM2. Ele executa imediatamente,
 aguarda `INVENTORY_SYNC_INTERVAL_SECONDS` (default 300) e tenta novamente após
 falhas transitórias de PostgreSQL ou Neo4j. `INVENTORY_SYNC_ENABLED=false`
 desabilita o worker sem alterar o restante do pipeline.

 O worker é single-threaded: um ciclo termina antes que o próximo comece. Ele
 trata SIGINT/SIGTERM e encerra sem iniciar novo ciclo. O `.env` local deve
 fornecer `DATABASE_URL`; credenciais não são defaults de código. O processo
 não registra URLs ou senhas.

Esta seção atualiza a decisão anterior: o worker agora existe como processo
dedicado, mas scheduler externo, eventos RabbitMQ e triggers continuam fora do
escopo.
