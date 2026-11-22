# Contexto Operacional — Sentinela de Preço R$ 0,01 (`CP-09`)

- **Objetivo:** auditar pedidos comerciais em aberto de clientes externos (`IDPESSOAFJ <> 1`) cadastrados com preço simbólico `R$ 0,01`, evitando faturamento com valor incorreto.
- **Chave de idempotência:** `CDPEDIDO` + `CDITEMPEDIDO` com renotificação após 24h.
- **Snapshot:** `Consultas Promovidas/snapshots/latest/sentinela-preco-zero-pedidos.json`.
- **Modo inicial:** `sombra` (roteado para `AUTOMACAO_ALERT_WHATSAPP`).
