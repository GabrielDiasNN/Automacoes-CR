---
name: enterprise-orchestration-contract
description: Use when orchestrating the end-to-end flow of automations across multiple technologies.
---

# 1. Purpose
Unificar o fluxo de ponta-a-ponta corporativo, definindo o gerenciamento de ExecId e garantindo a idempotência entre as camadas de VBA, VBScript, PowerShell, Node.js e Python.

# 2. When to Use
- Na concepção e execução de uma nova automação corporativa local.
- Ao integrar diferentes linguagens em um pipeline único e contínuo de execução.

# 3. Do Not Use When
- Para scripts ou macros isoladas que não compõem a esteira principal corporativa.

# 4. Related Skills
- automation-runtime-safety
- powershell-automation-monitor

# 5. Non-Negotiable Rules
- **Idempotência**: A automação deve ser projetada para ser reexecutada múltiplas vezes de forma segura, sem duplicar dados, corromper estados ou causar falhas.
- **ExecId**: Todo fluxo em execução deve possuir um ID de execução único rastreável de ponta a ponta em todos os logs e componentes.
- **Transições de Estado**: Deve-se registrar as mudanças de estado da automação de forma segura e atômica.
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
