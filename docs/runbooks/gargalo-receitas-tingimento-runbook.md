# Runbook Operacional: Gargalo Receitas Tingimento (CP-03)

[⬅️ Voltar para o Hub Central](../../README.md)

- **Componente / Diretório:** `Consultas Promovidas/gargalo-receitas-tingimento`
- **Criticidade:** `HIGH`
- **SLA de Recuperação:** `120 minutos`
- **Horários de Disparo:** `Seg-Sex as 07:30, 11:30, 14:30 e 17:30 [modo sombra]`
- **Dono do Negócio:** `Laboratorio de Receitas / Tinturaria`
- **Modo de Validação:** `sombra` (grupo de alerta `AUTOMACAO_ALERT_WHATSAPP`)

## Recuperação

1. Verifique logs em `Logs/gargalo-receitas-tingimento.jsonl` e diagnósticos no Dashboard.
2. Teste localmente com `powershell.exe -NoProfile -File "Consultas Promovidas/gargalo-receitas-tingimento/run.ps1" -DryRun`.
3. Faça **Requeue** na aba Execuções após normalizar o Oracle/WhatsApp.
