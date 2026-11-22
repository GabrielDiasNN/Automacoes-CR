# Sentinela de Preço R$ 0,01 em Pedidos Abertos (`CP-09`)

Consulta promovida (`Modelo 2`, `lib/python/promovidas/`) executada pelo Orchestrator em `queue_group="oracle"`.

- **Consulta:** `consulta.sql` (movida de `docs/oracle-schema/consultas/07_expedicao_pedidos_comercial/com_precos_carteira_pedidos_abertos.sql`)
- **Canais:** `whatsapp` (modo `sombra` em `AUTOMACAO_ALERT_WHATSAPP`) + `dashboard` (`/pcp`)
- **Regra de exceção:** `VLDIGITACAO <= 0.01`
- **Execução local segura:** `pwsh -File ".\Consultas Promovidas\sentinela-preco-zero-pedidos\run.ps1" -DryRun`
