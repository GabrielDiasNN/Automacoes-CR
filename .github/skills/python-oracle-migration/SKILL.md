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
- É PROIBIDO hardcodar credenciais ou usar arquivos .env em texto plano no repositório.
- Toda saída HTML deve ser sanitizada via html_escape para compatibilidade com Outlook.
- A contagem de lotes (receitas) deve respeitar a regra: Grupo 0 = individual, Grupo > 0 = 1 lote.

## Repo-Specific Constraints
- Utilizar obrigatoriamente a biblioteca `oracledb`.
- O envio de e-mail deve ser delegado à `lib\Lib-Email.psm1`.

## Related Skills
- automation-execution-contract
- log-standardization

## Troubleshooting
- **Caracteres corrompidos no Outlook**: Verifique se a função `html_escape` foi aplicada.
- **Assinatura sem imagens**: Garanta que o método `.Display()` foi chamado antes da injeção do HTML.
- **Falha de conexão Oracle**: Confirme se o modo Thick foi iniciado com o diretório correto do Client.

## Validation
A validação de paridade de dados deve ser feita comparando o JSON extraído pelo Python com um export CSV da aba de dados brutos do Excel original.

## Pre-Delivery Checklist
- [ ] Credenciais protegidas via .env e .gitignore?
- [ ] HTML sanitizado para o Outlook?
- [ ] Assinatura oficial preservada?
- [ ] Contagem de lotes validada?
- [ ] Arquivos temporários excluídos no final?
