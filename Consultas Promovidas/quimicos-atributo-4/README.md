# Químicos com Atributo 4 — Depósito 20 (`CP-10`)

Consulta promovida (`Modelo 2`, `lib/python/promovidas/`) executada pelo Orchestrator em `queue_group="oracle"`.

- **Consulta:** `consulta.sql` (movida de `docs/oracle-schema/consultas/01_beneficiamento_tingimento/bnf_monitoramento_atributos_produtos_quimicos.sql`)
- **Canais:** `whatsapp` (modo `sombra` em `AUTOMACAO_ALERT_WHATSAPP`) + `dashboard` (`/pcp`)
- **Regra de exceção:** `QUANTIDADE > 0` no depósito `20` com `IDGERAATRIESTO = 4` (renotificação a cada 4h até regularizar)
- **Execução local segura:** `pwsh -File ".\Consultas Promovidas\quimicos-atributo-4\run.ps1" -DryRun`
