# Runbook — Sincronismo Malha × Ribana (`CP-08`)

- **Criticidade:** Média (`sla_minutes = 120`)
- **Área dona:** PCP / Lojas
- **Motor:** `lib/python/promovidas/` (`Modelo 2`)

## Sintomas e diagnóstico rápido

1. Verificar o log da execução no Dashboard (`/execucoes`) ou em `Logs/sincronismo-malha-ribana.jsonl`.
2. Validar manualmente sem envio de WhatsApp:
   ```powershell
   pwsh -File ".\Consultas Promovidas\sincronismo-malha-ribana\run.ps1" -DryRun
   ```
3. Conferir se o snapshot local foi atualizado em `/pcp`.
