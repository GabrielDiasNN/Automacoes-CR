# Runbook — Sentinela de Preço R$ 0,01 (`CP-09`)

- **Criticidade:** Alta (`sla_minutes = 60`)
- **Área dona:** Comercial / Faturamento
- **Motor:** `lib/python/promovidas/` (`Modelo 2`)

## Sintomas e diagnóstico rápido

1. Verificar o log da execução no Dashboard (`/execucoes`) ou em `Consultas Promovidas/sentinela-preco-zero-pedidos/Logs/`.
2. Validar manualmente sem envio de WhatsApp:
   ```powershell
   pwsh -File ".\Consultas Promovidas\sentinela-preco-zero-pedidos\run.ps1" -DryRun
   ```
3. Quando retornar 0 linhas, nenhuma exceção é disparada e o snapshot registra `total_rows = 0`.
