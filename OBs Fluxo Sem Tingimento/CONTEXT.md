# CONTEXT — OBs Fluxo Sem Tingimento (OFST-06)

> Estado e decisões que um agente futuro precisa conhecer para mexer nesta automação sem quebrá-la.

## Estado atual

**Ativada em produção desde 16/07/2026, 17:00.** Criada em 16/07/2026 como "OB Fluxo 204" (`OB204-05`); renomeada para "OBs Fluxo Sem Tingimento" (`OFST-06`) no mesmo dia, junto com a adição do filtro de pedido comercial (R/S) e dos campos Artigo/Reduzido na mensagem — ver "Renomeação e novo escopo" abaixo. Schema, queries, destino WhatsApp e janela do cron validados contra o Oracle/WhatsApp reais (ver "Validação real" abaixo).

Registrada no Orchestrator central (`id=5`, `catalog_id=OFST-06`, `enabled=true`, `queue_group=oracle`) via `POST /api/automations/preflight` + `POST /api/automations`. Primeira execução real via cron (`0 5-20 * * 0-5`) rodou automaticamente às 17:00:15 do dia da ativação: `CRON_5_1784232000`, `status=SUCCESS`, `exit_code=2` ("nenhuma OB nova com estoque suficiente — nada a notificar", que é o resultado correto para o estado do Oracle naquele instante: OB #179605 precisava de 50 peças e o depósito 95 tinha 30). Pipeline completo (pré-flight → extração Oracle → validação → idempotência) validado de ponta a ponta em produção, sem erros.

Checklist de ativação (ver runbook) 100% concluído:

1. [x] `OFST_WHATSAPP_TARGET` encontrado (`554796989039-1616873564@g.us`, via `LIST_GROUPS`) e gravado no `.env` **local desta máquina**. Como `.env` não é versionado, **quem fizer o deploy em outra máquina precisa gravar essa mesma linha lá** — não é algo que "já vem pronto" com o clone do repo.
2. [x] Janela do cron confirmada com o Gabriel: `05:00–20:00`, Seg–Sáb — ver decisão D4.
3. [x] Renomeação + filtro de pedido comercial + artigo cru na mensagem (ver "Renomeação e novo escopo" abaixo).
4. [x] `test_ofst_simulation.py` rodado múltiplas vezes ao longo do dia contra Oracle real, sem fan-out.
5. [x] `run.ps1` executado manualmente uma vez (16/07/2026, 16:55) e depois automaticamente via cron do Orchestrator (16/07/2026, 17:00) — ambas com sucesso.
6. [x] Registrada no Orchestrator (`POST /api/automations/preflight` + `create`, `id=5`).

**Nada pendente.** Próxima execução agendada segue a cada 120 min, 05:00–19:00 Seg–Sex e 05:00–13:00 Sáb (ver decisão D9), sem intervenção manual necessária.

## Renomeação e novo escopo (16/07/2026)

A pedido do Gabriel, a automação foi renomeada de "OB Fluxo 204" (`OB204-05`) para "**OBs Fluxo Sem Tingimento**" (`OFST-06`) — pasta, id, slug, arquivos internos (`extract_ob_204.py`→`extract_ofst.py`, `test_ob_204_simulation.py`→`test_ofst_simulation.py`, `SQL-ObFluxo204.sql`→`SQL-ObsFluxoSemTingimento.sql`), classes Python (`ObFluxo204`→`ObSemTingimento`, `Ob204Error`→`OfstError`), artefatos runtime (`ob204_result.json`→`ofst_result.json`, `ob204_state.json`→`ofst_state.json`) e variável de ambiente (`OB204_WHATSAPP_TARGET`→`OFST_WHATSAPP_TARGET`). O código de fluxo Oracle continua `204` (`OB.CODIGO_FLUXO = 204` na query) — só o nome de exibição mudou, para deixar explícito que fluxo 204 = "direto para rama, sem tingimento".

Na mesma leva, dois pedidos de negócio foram incorporados à query principal:

1. **Filtro de pedido comercial**: excluir OBs cujo `PEDIDOCLIENTE` (`SGTPRD.PEDIDOCOMERCIAL`) termina em `R` ou `S`. Ver decisão D7.
2. **Artigo cru na mensagem**: além do reduzido (`CODIGO_REDUZIDO_CRU`, já existente), a mensagem agora informa o artigo cru (`CODIGO_ARTIGO_CRU`, de `SGTPRD.ENGEITEMESTOARTCRU.CDARTIGOCRU`). Ver decisão D8.

A mensagem WhatsApp também mudou de formato: quantidade agora é reportada em **peças** (não mais "un"), o número da OB vem em **negrito**, e o corpo lista Artigo + Reduzido em vez de só "Peça (Reduzido)". Ver `format_message.py`.

## Validação real (16/07/2026)

Rodado com acesso direto ao Oracle de produção (`SRVDB02:1521/dbprd`), não apenas lido do spec:

- **O spec errou os nomes de coluna/join.** `SGTPRD.OB` não tem coluna `ID` — a PK é `NUMERO_OB`. `SGTPRD.PEDPRODUCAOOB` não tem `ID_OB` — a FK para a OB é `NUMEROOB` (sem underscore). As queries, `validators.py`, `extract_ofst.py`, `format_message.py` e os testes já usam os nomes reais; se reintroduzir `ID`/`ID_OB` em qualquer lugar, a query falha com `ORA-00904`.
- **Cardinalidade OB→OB_PRODUTO→PEDPRODUCAOOB confirmada 1:1, sem fan-out real.** Não duplica linhas para fluxo 204/status 1 (checado com `GROUP BY ... HAVING COUNT(*) > 1`, zero ocorrências). Na query de estoque, `IDPECASPRODUTO`/`NUMERO_FINALIDADE`/`CODIGO_REDUZIDO` são PK das tabelas do lado direito dos joins, então a cardinalidade é 1:1 por construção — o otimizador confirma isso via *join elimination* do acesso a `ITENS_ESTOQUE` (ver plano de execução no cabeçalho de `SQL-EstoqueDeposito95.sql`). `QTD_PECAS_DISPONIVEIS` e `QTD_LINHAS_BRUTAS` deram idênticos em todos os testes.
- **`ENGEITEMESTOARTCRU` (artigo cru) confirmado 1:1 sem nulos** para 1293 OBs históricas de fluxo 204 (mesma amostragem da decisão D7/D8).
- **Planos de execução sem full table scan**, custo baixo (19 para a query de OBs, 6 para a de estoque com 2 códigos), usando os índices existentes (`OB_INDOB_DTENTRPEDIDO`, `OB_PROD_PK_OB_PRODUTO`, `PPRODUOB_IND_OB_NUMERO`, `GRPCPROD_INDPECASPRODUTOSIT`). Nenhum índice novo foi necessário.
- **`extract_ofst.py` e `test_ofst_simulation.py` rodaram de ponta a ponta** contra produção em múltiplas rodadas ao longo do dia — a contagem de OBs varia entre execuções porque a produção real muda em tempo real (OBs são montadas, novas são emitidas). Isso é esperado: não fixar um número de OBs como "o valor correto" em runbooks ou testes de integração manual.
- **Grupo WhatsApp "Expedição Tinturaria" encontrado** via `LIST_GROUPS`, inicialmente contornando um bug de serialização em `client.getChats()` do whatsapp-web.js (mesma classe de problema do CHANGELOG [1.1.7] para `sendMessage`) com um script de leitura descartável. O bug foi depois corrigido de vez em `lib/WhatsApp-Core.js` v2.8.1 (ver CHANGELOG [1.2.0]) — o comando documentado no README volta a funcionar sem workaround.

## Decisões

### D1 — `validators.py` é puro (sem I/O)

Nenhuma função de `validators.py` abre conexão ou lê arquivo; todas recebem linhas já buscadas. Quem faz I/O é `extract_ofst.py` (produção) e `test_ofst_simulation.py` (simulação).

**Por quê:** é o que permite testar 100% da regra de decisão sem Oracle (`Orchestrator/tests/test_ofst.py` roda no CI, que não tem banco). O spec pedia `validate_ob_query()` executando a própria query — isso amarraria toda a validação ao banco.

**Consequência:** a simulação e a produção chamam **as mesmas** funções de validação. O que o Gabriel aprova na FASE 1 é literalmente o código que roda depois.

### D2 — `COUNT(DISTINCT)` em vez do `COUNT()` do spec

`ITENS_ESTOQUE` e `TIPO_FINALIDADE_FIO` entram na query de estoque só como filtro (nenhuma coluna projetada). Se qualquer uma tiver cardinalidade > 1 por chave, o `COUNT()` simples infla o estoque → OB notificada sem peça real.

A query devolve `QTD_PECAS_DISPONIVEIS` (distinct, autoritativo) **e** `QTD_LINHAS_BRUTAS` (bruto). Divergência = fan-out, sinalizada por `EstoqueDeposito.tem_fan_out` e destacada na simulação.

**Se a simulação acusar fan-out:** os joins precisam de revisão de modelagem antes de ativar. Não é para "aceitar e seguir".

### D3 — Idempotência por OB, não por hash de lote

`ofst_state.json` guarda IDs de OB já notificados; só OB nova entra na mensagem. O state é podado para conter apenas OBs ainda notificáveis (OB montada sai da query e some do state; se voltar a ficar pendente, avisa de novo).

**Por quê:** o padrão hash-de-lote do OBP-04 não serve aqui. Com execução a cada 60 min e estoque flutuando, o hash mudaria sozinho e a mesma OB seria reavisada de hora em hora.

O commit do state é do `run.ps1` (`.tmp` → final) e **só após envio confirmado** — falha de WhatsApp nunca engole um aviso.

### D4 — Cron `0 5-20 * * 0-5` (confirmado com o Gabriel em 16/07/2026)

O spec pedia "a cada 60 minutos" sem janela. Propus 06:00–20:00 Seg–Sáb para não disparar WhatsApp de madrugada; o Gabriel ajustou o início para **05:00** (turno da Expedição Tinturaria começa mais cedo que o assumido). Domingo segue fora da janela — se isso mudar, é só trocar `cron_expression` no manifesto.

**Cuidado com o dia-da-semana:** `CronTrigger.from_crontab` (APScheduler, usado pelo Orchestrator) usa `0=Segunda...6=Domingo`, **não** a convenção Vixie/cron tradicional (`0=Domingo...6=Sábado`) — ver docstring em `Orchestrator/app/schemas/common.py`. "Segunda a Sábado" é `0-5`, não `1-6`. Eu mesmo errei isso na primeira versão do manifesto (usei `1-6`, que nessa convenção significa Terça a Domingo — o oposto do pretendido); corrigido para `0-5` comparando com o padrão já usado em `Montagem de Terceirizados/automation.manifest.json` (`0,30 5-21 * * 0-5`). Esse é o mesmo bug já registrado no CHANGELOG [1.1.8] para RB-01/RE-03/MT-02 — vale checar sempre que criar um cron novo neste repo.

### D9 — Cron ajustado para `["0 5-19/2 * * 0-4", "0 5-13/2 * * 5"]` (17/07/2026)

O Gabriel pediu para reduzir a frequência de 60 para **120 min** e encurtar a janela de sábado. Novo pedido: "a cada 120 min, 05:00–19:00, Seg–Sex e Sáb das 05:00–13:00" — ou seja, sábado deixou de acompanhar a janela de Seg–Sex (antes ambos iam até as 20:00) e passou a ter corte próprio às 13:00.

Como Seg–Sex e Sáb têm janelas de horário diferentes, não dá para expressar em um único `cron_expression` — usei o padrão de lista já existente em `OBs Paradas Fase/automation.manifest.json` (`cron_expression` como array; `_register_cron_schedule` em `Orchestrator/app/services/scheduler_runtime.py` registra um job por item da lista):

- `"0 5-19/2 * * 0-4"` — Seg–Sex, de 2 em 2h a partir das 05:00, última disparada às 19:00.
- `"0 5-13/2 * * 5"` — Sáb, de 2 em 2h a partir das 05:00, última disparada às 13:00.

Sintaxe `5-19/2` (range com step) validada com `CronTrigger.from_crontab` + `get_next_fire_time` antes de aplicar — gera exatamente `5,7,9,11,13,15,17,19`. Convenção de dia-da-semana continua `0=Segunda...6=Domingo` (ver D4); `0-4` = Seg–Sex, `5` = Sáb.

### D5 — O agendamento não vive no módulo

O spec pedia `orchestrator.py` com APScheduler dentro da automação. Aqui o agendamento é do **Orchestrator central**, que lê o campo `schedule` do `automation.manifest.json`. Um APScheduler próprio criaria um segundo escalonador paralelo, fora do controle do hub (sem telemetria, sem fila, sem lock).

O papel de "orchestrator" é do `run.ps1`, entrypoint declarado no manifesto.

### D6 — `fetch_all` da lib compartilhada ganhou `params`

`lib/python/oracle_extract.py::fetch_all` recebeu o kwarg opcional `params` (bind variables). Mudança retrocompatível — os 4 scripts existentes não passam `params` e seguem idênticos.

**Por quê:** esta é a primeira automação com query parametrizada. A alternativa seria duplicar o padrão fetch/serialize fora da lib, o que o CLAUDE.md proíbe.

Valores **sempre** via bind. Os nomes `:C0, :C1...` são gerados por `queries.build_estoque_sql`; nenhum dado externo é interpolado na string SQL.

### D7 — Filtro de pedido comercial (R/S) via `OFP.QUANTIDADE_ATUAL <> 0`, não via `DISTINCT`/agregação

O pedido do Gabriel foi simples ("filtrar `PEDIDOCLIENTE NOT LIKE '%R'` e `NOT LIKE '%S'`"), mas o caminho de join até `PEDIDOCOMERCIAL` não é direto a partir de `PEDPRODUCAOOB` — segue o mesmo padrão usado em `Montagem de Terceirizados/SQL-MontagemTerceirizados.sql` e na CTE `ENTREGA_OB` de `OBs Paradas Fase/SQL-ObsParadasFase.sql`:

```
PEDPRODUCAOOB -> OFORDENS (NUMEROPEDPRODUCAO+REDUZIDO)
              -> OFPEDIDO (NUMEROOF+NIVEL+REDUZIDO)
              -> ITENSPEDIDOQTDES (IDITENSPEDIDOQTDES)
              -> ITENSPEDIDOGRADE (IDITEMPEDGRADE)
              -> ITENSPEDIDOCOMERCIAL (PEDIDO+ITEMPEDIDO)
              -> PEDIDOCOMERCIAL (PEDIDO)
```

**Investigação de fan-out (antes de aplicar o filtro):** rodei essa cadeia de joins contra as 1293 OBs históricas reais de fluxo 204 (sem os filtros de STATUS/OBMONTADA, para ter amostra maior que as 1-3 OBs elegíveis num dado instante). Resultado: 18 OBs (~1,4%) tinham mais de uma linha de `OFPEDIDO` por OB, e em 7 dessas o `PEDIDOCLIENTE` resultante era **diferente** entre as linhas (não apenas duplicado) — um `WHERE`/filtro ingênuo teria excluído ou duplicado essas OBs de forma imprevisível.

**Causa raiz:** em todos os 7 casos investigados manualmente, uma das linhas tinha `PEDIDO=10078, ITEMPEDIDO=3, PEDIDOCLIENTE='0'` — um pedido "placeholder"/interno que convive na mesma `OFORDENS` com o pedido comercial real. `OBs Paradas Fase` já resolve exatamente esse problema com `WHERE OFP.QUANTIDADE_ATUAL <> 0` na sua CTE `ENTREGA_OB` — apliquei o mesmo filtro na condição do `LEFT JOIN` com `OFPEDIDO` (não no `WHERE` final, para não descartar a OB inteira quando não há pedido válido). Revalidado contra as mesmas 1293 OBs: **0 fan-out, 0 `PEDIDOCLIENTE` conflitante** com o filtro aplicado.

**OB sem pedido comercial (`PEDIDOCLIENTE` nulo) não é excluída.** O `WHERE` final trata `PED.PEDIDOCLIENTE IS NULL` como "sem sufixo R/S conhecido, mantém na lista" — decisão deliberada para não introduzir uma nova causa de silêncio (OB pronta que some da notificação só porque não tem pedido comercial rastreável). Se o Gabriel quiser o oposto (excluir OB sem pedido comercial), é uma mudança de uma linha no `WHERE`.

**Não simplificar removendo o filtro `QUANTIDADE_ATUAL <> 0` achando redundante** — sem ele, o fan-out volta e o filtro R/S fica não-determinístico (qual das duas linhas "vence" depende da ordem física de retorno do Oracle).

### D8 — Artigo cru via `SGTPRD.ENGEITEMESTOARTCRU`, mesmo padrão de Receitas Emitidas/OBs Paradas Fase

O Gabriel pediu para informar "Artigo Cru" na mensagem, ao lado do reduzido já existente. `SGTPRD.ENGEITEMESTOARTCRU.CDARTIGOCRU` (join por `CDREDUZIDO = CODIGO_REDUZIDO_CRU`) é o mesmo campo já usado em `Receitas Emitidas/SQL-ReceitasEmitidas.sql` (`ART.CDARTIGOCRU AS ARTIGO`) e `OBs Paradas Fase/SQL-ObsParadasFase.sql` (`TRIM(MAX(ART.CDARTIGOCRU)) AS CD_ARTIGO`). Validado contra o exemplo real do Gabriel: OB 181323, reduzido 152 → `CDARTIGOCRU='00489'` (a automação usa `int()` na coerção, que descarta os zeros à esquerda automaticamente → `489`, batendo com o exemplo).

Confirmado 1:1 sem nulos nas 1293 OBs históricas de fluxo 204 — tratado como campo obrigatório em `coerce_ob_row` (mesmo padrão dos demais campos), não como opcional.

## Armadilhas conhecidas

- **`ORA-01795`**: lista `IN` do Oracle aceita no máximo 1000 expressões. `queries.chunk_codigos` fatia em lotes de 900. Não remover achando que é over-engineering — o número de OBs de fluxo 204 pode crescer.
- **`test_ofst_simulation.py` não é suite pytest.** É um runner de linha de comando e não tem funções `test_*` — se ganhar uma, o CI passa a tentar abrir Oracle. Os testes automatizados ficam em `Orchestrator/tests/test_ofst.py`.
- **Métrica de comparação é `TOTAL_PECAS`**, nunca `KILOS_PROGRAMADOS` (que é carregado só para exibição/auditoria).
- **Não remover o filtro `OFP.QUANTIDADE_ATUAL <> 0`** da condição do join com `OFPEDIDO` — ver D7. Sem ele, o fan-out do pedido "placeholder" volta.
