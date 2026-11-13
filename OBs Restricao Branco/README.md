# OBs Restrição Branco (ORB-07)

Consulta OBs emitidas e não montadas, de qualquer fluxo, cuja classificação de
tingimento seja `6 = BRANCO` ou `9 = BRANCO 2 FIBRAS`. Quando o depósito 95
possui peças do mesmo reduzido cru com `FINALIDADE IN (3,4)` (`CORES CLARAS` ou
`BRANCO`), aloca o saldo
entre as OBs e prepara um aviso para o grupo Expedição Tinturaria.

| Item             | Valor                                                                   |
| ---------------- | ----------------------------------------------------------------------- |
| ID               | `ORB-07`                                                                |
| Entrypoint       | `run.ps1`                                                               |
| Canal            | WhatsApp — mesmo grupo da OFST-06                                       |
| Agenda planejada | A cada 60 min, 05:00–19:00 Seg–Sex; 05:00–13:00 Sáb                     |
| Estado           | Ativa no Orchestrator (`id=6`); primeiro envio confirmado em 25/08/2026 |

## Regra Oracle

- OB: `STATUS = 1`, `OBMONTADA = '0'`, pedido comercial não terminado em R/S.
- Cor: classificação obtida pela CTE `CLASSIFICACAO_OB` nas tabelas físicas
  (`OB_FASES`, `CADASTRO_RECEITAS`, `CLASSIFICACAO_COR`, `OB_PRODUTO`, `OB`,
  `ITENS_ESTOQUE`, `XX2_ENUMERATES`, `XX2_ENUMITEM` — em substituição à antiga
  view `VW_EXC_OB_PROD_CLASS_COR`), limitada a `(6, 9)`.
- `CODIGO_COR_DESENHO` é exibido para auditoria, mas não decide elegibilidade.
- Estoque: depósito 95, filial 2, qualidade sintética 1, estados `(0,16,18)` e
  contagem distinta de peças (`COUNT(DISTINCT IDPECASPRODUTO)`). O saldo restrito
  é **fixo por regra de negócio** em `FINALIDADES_PECA_ALVO = (3, 4)` (`CORES
CLARAS` e `BRANCO`). `COR_FINALIDADE` é consultada apenas para resolver as
  descrições oficiais e falhar de forma observável caso `3` ou `4` deixem de
  constar para as classes 6/9 (ampliar com a finalidade `1` é proibido). A
  consulta devolve, por reduzido, uma linha total e uma linha por finalidade.
- Prioridade: lojas por data de entrega; depois matriz. Dentro dessa fila, as
  OBs cobertas por inteiro alocam primeiro e as demais levam o saldo restante.
  O saldo é consumido por reduzido, evitando prometer a mesma peça para mais de
  uma OB.
- Cobertura parcial (desde 01/09/2026): basta **uma** peça restrita disponível
  para a OB ser anunciada. O card e a legenda exibem a ação direta de separação
  (`N pçs → usar X restr. + Y s/ restr.` ou `N pçs → usar N restr. (Completa)`).
- Complemento obrigatório (desde 02/09/2026): a OB parcial só entra se houver
  saldo **sem restrição** do mesmo reduzido para completar o lote — finalidades
  `1` (SEM RESTRIÇÃO) e `8` (FIO C/ RESÍDUO). Sem ele a Montagem não fecharia o
  lote, então a OB fica de fora e as peças restritas seguem livres para a
  próxima OB. Ficam de fora, portanto, a OB sem nenhuma peça restrita e a OB
  cujo lote não fecha.
- Visualização (desde 13/11/2026): `format_message.py` (com
  `lib/python/card_pagination.py`) pagina em blocos de até `15` OBs por card
  PNG (`MAX_OBS_PER_PAGE = 15`, `Pillow` com fontes TrueType `Arial`/`DejaVuSans`
  e fallback proporcional) — `card.png` + `message.txt` quando há 1 página
  (`AUTO`) ou `card_01.png`..`card_NN.png` + `cards_manifest.json` quando há mais
  de 1 página (`-Mode BATCH`), sem truncar nenhuma OB. Cada linha exibe artigo de
  três dígitos (`32` → `032`), reduzido, restrições (`3 — CORES CLARAS; 4 —
  BRANCO`), ação de separação, filial destino e data de entrega; e legenda
  pesquisável pelo número da OB no WhatsApp. Campos de auditoria (`Fluxo`, `Cor
  programada`, `Classificação` e saldo bruto) ficam apenas em `orb_result.json`
  e nos logs.

## Simulação segura

```powershell
.venv\Scripts\python.exe "OBs Restricao Branco\test_orb_simulation.py"
```

A simulação consulta o Oracle em modo somente leitura, não cria state, não gera
mensagem e não envia WhatsApp.

## Idempotência

`orb_state.json` registra uma notificação por ciclo pendente da OB. O arquivo
temporário só é consolidado após envio confirmado (e em envio em lote paginado,
`Lib-WhatsAppBatch.psm1` preserva no state apenas as OBs das páginas entregues,
removendo as páginas com falha para reavaliação no ciclo seguinte); quando não
há envio, o state ainda é reconciliado para remover OBs que saíram da seleção.

No primeiro ciclo houve um falso sucesso do `whatsapp-web.js`: o processo terminou
com `sendMessage` sem ID e a mensagem não apareceu imediatamente no histórico. O
motor agora aguarda `waitUntilMsgSent`, aceita o ID retornado ou o evento
`message_create` (incluindo o identificador interno `$1`) e falha sem consolidar o
state quando nenhuma confirmação existe. A mensagem operacional foi posteriormente
confirmada no grupo com ACK 1 e as seis OBs foram reconciliadas no state; o ciclo
seguinte saiu com código 2, sem novo envio.

O destino real permanece em `OFST_WHATSAPP_TARGET`, compartilhado
intencionalmente porque as duas automações usam o mesmo grupo. Nenhum ID de
grupo é versionado.

Runbook: [docs/runbooks/obs-restricao-branco-runbook.md](../docs/runbooks/obs-restricao-branco-runbook.md).
