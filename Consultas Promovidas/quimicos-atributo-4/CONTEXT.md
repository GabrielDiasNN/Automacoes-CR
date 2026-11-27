# Contexto Operacional — Químicos com Atributo 4 (`CP-10`)

- **Objetivo:** monitorar entradas de produtos químicos no depósito `20` com `IDGERAATRIESTO = 4` (atributo genérico sem lote/concentração real, que impacta emissão e controle de receitas) enquanto houver saldo líquido positivo (`QUANTIDADE > 0`).
- **Chave de idempotência:** `NF` + `REDUZIDO` com renotificação após `1h` até o saldo zerar por transferência/regularização (`NRTIPOMOVIMENTO = 734`) ou consumo.
- **Reserva para receitas (no card):** soma de `SGTPRD.MOVTO_RECEITA.QUANTIDADE` nos últimos 30 dias com `MOVCONFIRMADO = 0` e `STATUSPESAGEMRECEITA <> 3` (`RESERVA_RECEITAS`).
- **Snapshot:** `Consultas Promovidas/snapshots/latest/quimicos-atributo-4.json`.
- **Modo inicial:** `sombra` (roteado para `AUTOMACAO_ALERT_WHATSAPP`).
