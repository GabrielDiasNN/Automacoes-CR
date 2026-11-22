# Contexto Operacional — Sincronismo Malha × Ribana (`CP-08`)

- **Objetivo:** monitorar o sincronismo entre malha principal e ribana na rede de lojas Costa Rica (`CODIGO_GRUPO`), interceptando descasamentos críticos antes da expedição incompleta.
- **Chave de idempotência:** `CODIGO_GRUPO` com renotificação após 24h.
- **Snapshot:** `Consultas Promovidas/snapshots/latest/sincronismo-malha-ribana.json`.
- **Modo inicial:** `sombra` (roteado para `AUTOMACAO_ALERT_WHATSAPP` até validação de limiares).
