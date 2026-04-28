---
name: vba-enterprise-core
description: Use when maintaining VBA enterprise components, Outlook COM integration, and VBE safety.
---

# 1. Purpose
Padronizar a manutenção segura de componentes VBA legados, automações do Outlook via motor COM e a governança na sincronização de arquivos `.bas` e `.cls`.

# 2. When to Use
- Durante o suporte ou desenvolvimento em projetos `.xlsm` corporativos.
- Ao criar integrações de disparo de e-mails usando a API Outlook COM.
- Para exportação/importação de módulos no repositório local.

# 3. Do Not Use When
- Em novos fluxos de processamento lógico de alta performance (neste caso, prefira Python).

# 4. Related Skills
- html-css-enterprise-standard

# 5. Non-Negotiable Rules
- **VBE Safe**: Nunca alterar o código diretamente nos módulos do Excel (VBE) sem espelhar os respectivos arquivos (`.bas`/`.cls`) no controle de versão.
- **Outlook COM**: É imperativo efetuar a liberação explícita de objetos da memória (`Set obj = Nothing`) para evitar memory leaks na integração com o Outlook.
## Purpose
- Conforme diretrizes globais.

## When to Use
- Conforme diretrizes globais.

## Do Not Use When
- Conforme diretrizes globais.

## Related Skills
- Conforme diretrizes globais.

## Non-Negotiable Rules
- Conforme diretrizes globais.

## Repo-Specific Constraints
- Conforme diretrizes globais.

## Validation
- Conforme diretrizes globais.

## Troubleshooting
- Conforme diretrizes globais.

## Pre-Delivery Checklist
- Conforme diretrizes globais.

