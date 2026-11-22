# Runbook Operacional: Qualidade Separacao Montagem (CP-05)

[⬅️ Voltar para o Hub Central](../../README.md)

- **Componente / Diretório:** `Consultas Promovidas/qualidade-separacao-montagem`
- **Criticidade:** `HIGH`
- **SLA de Recuperação:** `60 minutos`
- **Horários de Disparo:** `A cada 2h das 06:00 as 18:00 (Seg-Sab) [modo sombra]`
- **Dono do Negócio:** `Qualidade / Beneficiamento`
- **Modo de Validação:** `sombra` (grupo de alerta `AUTOMACAO_ALERT_WHATSAPP`)

## Recuperação

1. Verifique logs em `Logs/qualidade-separacao-montagem.jsonl` e diagnósticos no Dashboard.
2. Teste localmente com `powershell.exe -NoProfile -File "Consultas Promovidas/qualidade-separacao-montagem/run.ps1" -DryRun`.
3. Faça **Requeue** na aba Execuções após normalizar o Oracle/WhatsApp.
