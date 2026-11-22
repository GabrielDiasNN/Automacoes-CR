# Runbook Operacional: Pulmao e Autonomia Ramas (CP-02)

[⬅️ Voltar para o Hub Central](../../README.md)

- **Componente / Diretório:** `Consultas Promovidas/rama-pulmao-autonomia`
- **Criticidade:** `MEDIUM`
- **SLA de Recuperação:** `60 minutos`
- **Horários de Disparo:** `A cada 2h das 05:00 as 19:00 (Seg-Sex) e 05:00 as 13:00 (Sab) [modo sombra]`
- **Dono do Negócio:** `PCP / Acabamento`
- **Modo de Validação:** `sombra` (grupo de alerta `AUTOMACAO_ALERT_WHATSAPP`)

## Recuperação

1. Verifique logs em `Logs/rama-pulmao-autonomia.jsonl` e diagnósticos no Dashboard.
2. Teste localmente com `powershell.exe -NoProfile -File "Consultas Promovidas/rama-pulmao-autonomia/run.ps1" -DryRun`.
3. Faça **Requeue** na aba Execuções após normalizar o Oracle/WhatsApp.
