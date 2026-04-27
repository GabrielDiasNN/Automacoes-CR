---
name: python-oracle-migration
description: Use when migrating Excel/VBA automations to a native Python architecture with Oracle extraction and HTML reporting.
---

# SKILL: Migração Nativa Python + Oracle (VBA-Free)

## Purpose
Padronizar a migração de automações legadas baseadas em Excel/VBA/PowerQuery para scripts nativos Python conectados diretamente ao banco Oracle, visando performance e estabilidade.

## When to Use
Use when:
- Uma automação via Excel/VBA apresenta falhas constantes de execução.
- O tempo de processamento do PowerQuery/VBA é superior a 30 segundos.
- Há necessidade de maior segurança na gestão de credenciais.

## Do Not Use When
- A automação exige interface visual de usuário (formulários complexos) que não pode ser facilmente migrada para e-mail/dashboard.
- O custo de migração supera significativamente os ganhos operacionais.

## Non-Negotiable Rules
- **Native-First Architecture**: Always try direct extraction via Python first.
- **Hybrid-Fallback Strategy**: Implement a silent fallback to Excel COM if the Oracle connection is killed (`ORA-00028`), ensuring the automation never stops.
- **Secure File-Payload**: Use temporary `.data_ExecId.json` files for IPC between extraction and validation to prevent PowerShell buffer corruption.
- **ASCII-Safe Core**: Use only ASCII or Unicode escapes in Python source for logs/UI strings to prevent encoding regressions.
- **SQL CTE Optimization**: Use `WITH` clauses and `FIRST_ROWS` hints to ensure query speed and stability.
- Proibido hardcodar credenciais; use `.env` carregado no runtime do processo.

## Related Skills
- `automation-execution-contract`: Execution IDs and exit codes.
- `log-standardization`: Logging patterns.
- `ai-native-development-standard`: General repository standards.

## Repo-Specific Constraints
- Utilizar a biblioteca `oracledb` com modo Thick se disponível.
- Delegar o envio de e-mail ao `Send-OutlookEmail` (PowerShell) para garantir o **Outlook-Safe Protocol**.

## Troubleshooting
- **Caracteres corrompidos no Outlook**: Verifique se a função `html_escape` foi aplicada.
- **Assinatura sem imagens**: Garanta que o método `.Display()` foi chamado antes da injeção do HTML.
- **Falha de conexão Oracle**: Confirme se o modo Thick foi iniciado com o diretório correto do Client.

## Validation
- Compare o volume de dados extraídos com o Excel legado.
- Valide se o arquivo `.data_ExecId.json` é gerado corretamente no disco antes de ser consumido.

## Pre-Delivery Checklist
- [ ] Fallback Híbrido implementado no orquestrador?
- [ ] IPC utiliza Secure File-Payload para dados extensos?
- [ ] Código-fonte é ASCII-Safe (sem acentos crus)?
- [ ] SQL utiliza CTEs e hints de performance?
- [ ] Arquivos temporários são excluídos no `finally`?
