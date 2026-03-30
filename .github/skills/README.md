# Skills Canônicos do Repositório

Este diretório é a fonte canônica de skills do workspace.

## Regra Oficial

- Local canônico: `.github/skills`
- Local descontinuado: `.agents/skills`
- Não manter skills duplicados em múltiplos diretórios para evitar drift.

## Estrutura Esperada

Cada skill deve seguir o padrão:

- Pasta em kebab-case: `<nome-do-skill>/`
- Arquivo principal: `SKILL.md`
- Frontmatter com `name` e `description` coerentes com o nome da pasta.

## Governança de Mudança

1. Criar ou alterar sempre em `.github/skills`.
2. Validar sintaxe YAML do frontmatter.
3. Garantir descrição no formato "Use when..." para facilitar discovery.
4. Revisar consistência com os padrões enterprise do repositório.
