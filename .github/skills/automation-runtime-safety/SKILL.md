---
name: automation-runtime-safety
description: Use when standardizing logs, diagnostics, and ensuring Zero Trust Security across the pipeline.
---

# 1. Purpose
Garantir a segurança operacional por meio da abordagem Zero Trust, com padronização rigorosa de logs estruturados e geração de diagnósticos limpos na esteira de automação.

# 2. When to Use
- Na implementação de frameworks de logs e monitoramento de automações.
- Para gerenciar segredos e credenciais de forma segura.

# 3. Do Not Use When
- Em testes locais e temporários que não terão impacto no ambiente de produção.

# 4. Related Skills
- enterprise-orchestration-contract

# 5. Non-Negotiable Rules
- **Segurança Zero Trust**: É estritamente proibido qualquer hardcode de senhas, tokens ou credenciais no código. Deve-se forçar o uso de variáveis de ambiente (`.env`) ou gerenciadores de segredos.
- **Logs Estruturados**: Os logs devem ser limpos, padronizados, rastreáveis pelo ExecId e conter os níveis claros de criticidade (INFO, WARN, ERROR).
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
