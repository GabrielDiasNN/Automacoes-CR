---
name: nodejs-communications
description: Use when building communication modules like WhatsApp integrations or orchestrating via BAT.
---

# 1. Purpose
Gerenciar disparos de comunicações automatizadas (como notificações de WhatsApp) via Node.js em conjunto com scripts BAT/CMD para a etapa inicial de execução (bootstrap).

# 2. When to Use
- Na implementação e gerenciamento de disparos de mensagens WhatsApp.
- Ao construir scripts `.bat` ou `.cmd` de orquestração local.

# 3. Do Not Use When
- Para disparos de e-mails corporativos tradicionais baseados no Outlook COM (usar VBA).

# 4. Related Skills
- enterprise-orchestration-contract

# 5. Non-Negotiable Rules
- **Assincronicidade Limpa**: Utilizar `async/await` no Node.js aliado a um rigoroso tratamento de exceções.
- **Inicialização Segura**: Scripts BAT/CMD de entrada devem conter controles robustos de falha e transições limpas baseadas em `errorlevel`.
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
