# Contexto Operacional — Fila Programada por Máquina de Tingimento (`CP-07`)

- **Objetivo:** dar visibilidade da fila programada à frente por máquina de tingimento (UPs ainda não iniciadas) e sinalizar quando há UPs atrasadas (`QT_ATRASADAS > 0`).
- **Chave de idempotência:** `MQ` com renotificação após 12h.
- **Snapshot:** `Consultas Promovidas/snapshots/latest/fila-maquina-tingimento.json`.
- **Modo inicial:** `sombra` (roteado para `AUTOMACAO_ALERT_WHATSAPP` até validação de limiares).
