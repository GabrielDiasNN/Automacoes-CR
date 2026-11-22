# Fila Programada por Máquina de Tingimento (`CP-07`)

Consulta promovida (`Modelo 2`, `lib/python/promovidas/`) executada pelo Orchestrator em `queue_group="oracle"`.

- **Consulta:** `consulta.sql` (movida de `docs/oracle-schema/consultas/01_beneficiamento_tingimento/bnf_fila_programada_por_maquina_tingimento.sql`)
- **Canais:** `whatsapp` (modo `sombra` em `AUTOMACAO_ALERT_WHATSAPP`) + `dashboard` (`/pcp`)
- **Regra de exceção:** `QT_ATRASADAS > 0`
- **Execução local segura:** `pwsh -File ".\Consultas Promovidas\fila-maquina-tingimento\run.ps1" -DryRun`
