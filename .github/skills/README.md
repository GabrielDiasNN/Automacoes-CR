# Skills Canonicos do Repositorio

Este diretorio e a fonte canonica de skills do workspace.

## Regra Oficial

- Local canonico: `.github/skills`
- Local descontinuado: `.agents/skills`
- Nao manter skills duplicados em multiplos diretorios para evitar drift.
- Skills novas devem nascer com responsabilidade clara e relacionamento explicito com as demais.

## Taxonomia do Workspace

O conjunto atual de skills esta organizado em quatro grupos:

- Fundacao compartilhada: contratos transversais usados por varias automacoes.
- Orquestracao: define como as camadas VBS, Excel/VBA, monitor e canais se encaixam.
- Runtime e canais: especializa PowerShell, BAT, Node.js, Outlook e WhatsApp.
- Governanca e apresentacao: disciplina de VBA, HTML e CSS para VBE e saidas geradas.

## Estrutura Esperada

Cada skill deve seguir o padrao:

- Pasta em kebab-case: `<nome-do-skill>/`
- Arquivo principal: `SKILL.md`
- Recursos opcionais em um nivel abaixo: `references/`, `scripts/`, `assets/`
- Frontmatter com `name` e `description` coerentes com o nome da pasta

## Frontmatter Canonico

Use somente campos oficialmente suportados pelo sistema de skills:

- Obrigatorios:
  - `name`
  - `description`
- Opcionais:
  - `argument-hint`
  - `user-invocable`
  - `disable-model-invocation`

Evite metadados ad hoc no YAML, como `version`, `owner` ou `language`. Essas informacoes devem morar no corpo da skill ou em referencias locais para evitar falhas silenciosas de discovery.

## Estrutura Interna Obrigatoria

Toda SKILL.md deve ter, no minimo, estas secoes:

1. `Purpose`
2. `When to Use`
3. `Do Not Use When`
4. `Related Skills`
5. `Non-Negotiable Rules`
6. `Repo-Specific Constraints`
7. `Validation`
8. `Troubleshooting`
9. `Pre-Delivery Checklist`

Uma skill pode ter secoes extras como `Architecture Overview`, `Execution Flow`, `Runtime Contract` ou `Implementation Workflow`, desde que a responsabilidade continue clara.

## Regras de Descoberta

- `description` deve comecar com `Use when...` e explicar quando usar esta skill em vez de outra parecida.
- `Related Skills` deve listar complementos naturais e fronteiras de ownership.
- `Do Not Use When` e obrigatoria para reduzir sobreposicao entre skills.
- Contratos transversais devem existir em uma unica fonte; outras skills devem referenci-los, nao duplicar blocos longos.

## Regras de Governanca

1. Criar ou alterar sempre em `.github/skills`.
2. Validar sintaxe YAML do frontmatter.
3. Garantir descricao no formato `Use when...` para facilitar discovery.
4. Revisar consistencia com os padroes enterprise do repositorio.
5. Declarar `Related Skills` em toda skill nova ou reescrita.
6. Se uma regra vale para varias linguagens ou varias automacoes, extraia para uma skill-base ou referencia local compartilhada.
7. Nao usar a mesma skill para misturar arquitetura, runtime, canal e governanca sem uma necessidade clara.

## Criterio Para Criar Nova Skill

Crie uma nova skill quando houver um fluxo reutilizavel, especializado e recorrente.

Nao crie nova skill quando:

- O conteudo cabe melhor em `references/` de uma skill existente.
- A regra e apenas um detalhe operacional de uma skill maior.
- O objetivo pode ser resolvido com uma melhoria de `description`, `Related Skills` ou `Repo-Specific Constraints`.

## Fluxo de Manutencao

1. Identificar se a mudanca afeta fundacao compartilhada, runtime, canal ou governanca.
2. Atualizar primeiro a fonte central do contrato, depois as skills consumidoras.
3. Revisar se as memorias do repositorio continuam refletidas no local correto.
4. Executar validacao de markdown em dry run antes de concluir.
5. Fazer revisao manual de discovery para garantir que a skill continua facil de escolher.

## Validacao Automatizada

- `Tools/Test-SkillsGovernance.ps1` valida local canonico, frontmatter permitido, discovery por `description` e secoes obrigatorias.
- `Tools/ValidarAutomacoes.ps1 -OnlyGovernance` agrega a governanca de skills com os checks de governanca ja existentes do repositorio.
- A task recomendada no workspace para revisao rapida e `Validacao: Skills`.
