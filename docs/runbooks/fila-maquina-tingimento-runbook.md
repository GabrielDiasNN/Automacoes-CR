# Runbook — Fila Máquina Tingimento (`CP-07`)

- **Criticidade:** Média (`sla_minutes = 60`)
- **Área dona:** PCP / Tinturaria
- **Motor:** `lib/python/promovidas/` (`Modelo 2`)

## Sintomas e diagnóstico rápido

1. Verificar o log da execução no Dashboard (`/execucoes`) ou em `Consultas Promovidas/fila-maquina-tingimento/Logs/`.
2. Validar manualmente sem envio de WhatsApp:
   ```powershell
   pwsh -File ".\Consultas Promovidas\fila-maquina-tingimento\run.ps1" -DryRun
   ```
3. Conferir se a fila Oracle (`ORACLE_DRIVER_MODE=queue`) está ativa em `/sistema`.
