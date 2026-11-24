# Runbook — Químicos com Atributo 4 (`CP-10`)

- **Criticidade:** Alta (`sla_minutes = 60`)
- **Área dona:** Laboratório de Receitas / Tinturaria / Almoxarifado
- **Motor:** `lib/python/promovidas/` (`Modelo 2`)

## Sintomas e diagnóstico rápido

1. Verificar o log da execução no Dashboard (`/execucoes`) ou em `Logs/quimicos-atributo-4.jsonl`.
2. Validar manualmente sem envio de WhatsApp:
   ```powershell
   pwsh -File ".\Consultas Promovidas\quimicos-atributo-4\run.ps1" -DryRun
   ```
3. Quando retornar 0 linhas (todos os itens regularizados com saldo `<= 0` no atributo `4`), nenhuma exceção é disparada e o snapshot registra `total_rows = 0`.
4. Ao identificar item pendente (`NF`, `DEPOSITO`, `REDUZIDO`, `DESCRICAO`, `QUANTIDADE`), acionar o almoxarifado/laboratório para regularização do atributo de estoque no ERP (ex.: transferência de concentração/atributo).
