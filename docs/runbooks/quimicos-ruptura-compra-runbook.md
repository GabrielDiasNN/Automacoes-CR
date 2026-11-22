# Runbook Operacional: Sentinela Ruptura Quimicos (CP-04)

[⬅️ Voltar para o Hub Central](../../README.md)

- **Componente / Diretório:** `Consultas Promovidas/quimicos-ruptura-compra`
- **Criticidade:** `HIGH`
- **SLA de Recuperação:** `180 minutos`
- **Horários de Disparo:** `Seg-Sex as 08:00 [modo sombra]`
- **Dono do Negócio:** `PCP / Compras / Tinturaria`
- **Modo de Validação:** `sombra` (grupo de alerta `AUTOMACAO_ALERT_WHATSAPP`)

## Recuperação

1. Verifique logs em `Logs/quimicos-ruptura-compra.jsonl` e diagnósticos no Dashboard.
2. Teste localmente com `powershell.exe -NoProfile -File "Consultas Promovidas/quimicos-ruptura-compra/run.ps1" -DryRun`.
3. Faça **Requeue** na aba Execuções após normalizar o Oracle/WhatsApp.
4. **Limitação conhecida em sombra:** enquanto `SEGURANCA_KG=0`, `COBERTURA_MIN_DIAS=0` e `PRAZO_PADRAO_DIAS=NULL` na `CTE PARAMETROS` de `consulta.sql`, apenas rupturas já consumadas (`ESTOQUE_DISPONIVEL_KG - PREVISTO_CONFIRMADO_KG <= 0`) geram `CRITICO`; itens sem `PRAZOENTREGA > 0` ficam como `DADOS_INCOMPLETOS` até calibração com PCP/Compras.
