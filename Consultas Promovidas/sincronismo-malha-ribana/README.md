# Sincronismo Malha × Ribana (`CP-08`)

Consulta promovida (`Modelo 2`, `lib/python/promovidas/`) executada pelo Orchestrator em `queue_group="oracle"`.

- **Consulta:** `consulta.sql` (movida de `docs/oracle-schema/consultas/09_pcp_kpis_gestao/pcp_sincronismo_malha_ribana.sql`)
- **Canais:** `whatsapp` (modo `sombra` em `AUTOMACAO_ALERT_WHATSAPP`) + `dashboard` (`/pcp`)
- **Regra de exceção:** `ORDEM_PRIORIDADE <= 2` (descasamento crítico Malha/Ribana ou atraso)
- **Execução local segura:** `pwsh -File ".\Consultas Promovidas\sincronismo-malha-ribana\run.ps1" -DryRun`
