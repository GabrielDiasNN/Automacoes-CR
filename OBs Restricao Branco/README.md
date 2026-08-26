# OBs Restrição Branco (ORB-07)

Consulta OBs emitidas e não montadas, de qualquer fluxo, cuja classificação de
tingimento seja `6 = BRANCO` ou `9 = BRANCO 2 FIBRAS`. Quando o depósito 95
possui peças do mesmo reduzido cru com `FINALIDADE IN (3,4)` (`CORES CLARAS` ou
`BRANCO`), aloca o saldo
entre as OBs e prepara um aviso para o grupo Expedição Tinturaria.

| Item | Valor |
|---|---|
| ID | `ORB-07` |
| Entrypoint | `run.ps1` |
| Canal | WhatsApp — mesmo grupo da OFST-06 |
| Agenda planejada | A cada 120 min, 05:00–19:00 Seg–Sex; 05:00–13:00 Sáb |
| Estado | Ativa no Orchestrator (`id=6`); primeiro envio confirmado em 25/08/2026 |

## Regra Oracle

- OB: `STATUS = 1`, `OBMONTADA = '0'`, pedido comercial não terminado em R/S.
- Cor: classificação obtida de `VW_EXC_OB_PROD_CLASS_COR`, limitada a `(6, 9)`.
- `CODIGO_COR_DESENHO` é exibido para auditoria, mas não decide elegibilidade.
- Estoque: depósito 95, filial 2, qualidade sintética 1, estados `(0,16,18)`
  e contagem distinta de peças. As finalidades aceitas **não são fixas**: saem
  de `COR_FINALIDADE` para as classificações 6 e 9 — hoje
  `{1, 3, 4, 6, 8, 12, 13}`. A consulta devolve, por reduzido, uma linha total
  (saldo autoritativo) e uma linha por finalidade para auditoria.
- Prioridade: lojas por data de entrega; depois matriz. O saldo é consumido por
  reduzido, evitando prometer a mesma peça para mais de uma OB.
- Mensagem: artigo com três dígitos (`32` → `032`) e cor com dois dígitos
  (`00001` → `01`). A linha de restrição lista as finalidades com saldo (ex.:
  `1 — SEM RESTRIÇÃO; 3 — CORES CLARAS`), conforme o estoque encontrado.

## Simulação segura

```powershell
.venv\Scripts\python.exe "OBs Restricao Branco\test_orb_simulation.py"
```

A simulação consulta o Oracle em modo somente leitura, não cria state, não gera
mensagem e não envia WhatsApp.

## Idempotência

`orb_state.json` registra uma notificação por ciclo pendente da OB. O arquivo
temporário só é consolidado após envio confirmado; quando não há envio, o state
ainda é reconciliado para remover OBs que saíram da seleção.

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
