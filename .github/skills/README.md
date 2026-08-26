# Skills Canônicas do Repositório

Este diretório é a fonte canônica de skills do workspace.

O projeto atual é 100% nativo, com stack consolidada em Python, PowerShell e Node.js. Skills legadas de migração para Python ou de runtime VBA não fazem mais parte da taxonomia ativa e não devem ser reintroduzidas em discovery, `Related Skills` ou documentação operacional.

## Regra Oficial

- Local canônico das skills de padrão: `.github/skills`
- Mirror declarado delas: `.gemini/skills` (junctions para `.github/skills`)
- Fonte única das skills operacionais do projeto: `.claude/skills`
- Mirror declarado delas: `.agents/skills` (junctions para `.claude/skills`)
- Não manter skills duplicadas em múltiplos diretórios para evitar drift: mirror é link, nunca cópia — `Tools/Test-SkillsGovernance.ps1` reprova cópia real, alvo divergente e mirror órfão.
- Mirror não é versionado (ver `.gitignore`): é artefato local, recriado por `pwsh -File Tools\New-SkillMirrors.ps1`. Rode-o após clonar o repositório e sempre que criar ou renomear uma skill — skill nova sem espelho reprova a governança com `GEMINI_SKILL_MIRROR_MISSING` (skills de padrão em `.github/skills`) ou `AGENTS_SKILL_MIRROR_MISSING` (skills operacionais em `.claude/skills`, cobrado apenas quando `.agents/skills` já existe — o mirror inteiro é opcional). Use `-Force` para substituir um mirror que virou cópia real.
- Melhorar skill existente antes de propor uma skill nova.

## Taxonomia Ativa do Workspace

O conjunto ativo de 7 skills está organizado nas seguintes fronteiras de responsabilidade:

1. **Fundação**
   - `ai-native-development-standard`: governança de contexto, documentação AI-Native, discovery e evolução das skills.

2. **Contratos Transversais**
   - `enterprise-orchestration-contract`: `ExecId`, idempotência, entrypoints, estados e handoff entre runtimes.
   - `automation-runtime-safety`: Zero Trust, logs, severidade, encoding e falha segura.

3. **Runtimes e Canais**
   - `python-enterprise-standard`: desenvolvimento backend, qualidade Mypy/Pylint, Pydantic, e regras estritas para processamento Python.
   - `powershell-automation-monitor`: scripts corporativos, monitores, módulos compartilhados e governança PowerShell.
   - `nodejs-communications`: WhatsApp, headless e bootstrap `.bat`/`.cmd` sem ownership de orquestração geral.

4. **Apresentação**
   - `html-css-enterprise-standard`: dashboard, HTML corporativo, assets compartilhados e separação entre UI e negócio.

## Estrutura Esperada

Cada skill deve seguir o padrão:

- Pasta em kebab-case: `<nome-da-skill>/`
- Arquivo principal: `SKILL.md`
- Recursos opcionais em um nível abaixo: `references/`, `scripts/`, `assets/`
- Frontmatter com `name` e `description` coerentes com o nome da pasta

## Frontmatter Canônico

Use somente campos oficialmente suportados pelo sistema de skills:

- Obrigatórios:
  - `name`
  - `description`
- Opcionais:
  - `argument-hint`
  - `user-invocable`
  - `disable-model-invocation`

Não adicione metadados ad hoc no YAML. Ownership, exemplos ou detalhe operacional devem viver no corpo do `SKILL.md` ou em `references/`.

## Estrutura Interna Obrigatória

Toda `SKILL.md` deve conter, no mínimo, estas seções em `##`:

1. `Purpose`
2. `When to Use`
3. `Do Not Use When`
4. `Related Skills`
5. `Non-Negotiable Rules`
6. `Repo-Specific Constraints`
7. `Validation`
8. `Troubleshooting`
9. `Pre-Delivery Checklist`

Seções extras são permitidas quando agregam decisão operacional real, não texto ornamental.

## Regras de Descoberta

- `description` deve começar com `Use when`.
- `description` deve diferenciar a skill de outra skill próxima.
- `Do Not Use When` é obrigatória para reduzir overlap.
- `Related Skills` deve citar apenas skills existentes na taxonomia ativa.
- Regras transversais devem ter fonte única; skills consumidoras devem referenciar, não duplicar.

## Regras de Governança

1. Criar ou alterar skills sempre em `.github/skills`.
2. Bloquear placeholders como `Conforme diretrizes globais.`.
3. Não citar skills legadas ou inexistentes em `Related Skills` ou na taxonomia.
4. Referenciar artefatos reais do repositório nas seções operacionais sempre que a regra depender da implementação local.
5. Manter `README.md`, `CONTEXT.md`, `SECURITY.md`, `GEMINI.md` e `CHANGELOG.md` coerentes com a stack atual quando a mudança tocar governança.
6. Manter documentação Markdown em UTF-8 sem BOM, com acentuação normal em PT-BR e sem mojibake.

## Critério Para Criar Nova Skill

Crie uma nova skill apenas quando houver:

- fluxo recorrente e especializado;
- fronteira clara de ownership;
- dificuldade real de encaixar o conteúdo em uma das 7 skills atuais ou em `references/` associadas.

Não crie nova skill quando:

- o conteúdo cabe em `references/` de uma skill existente;
- a regra é apenas um detalhe de runtime, canal ou governança já coberto;
- o problema é de discovery e pode ser resolvido com `description`, `Do Not Use When` ou `Related Skills`.

## Fluxo de Manutenção

1. Identificar qual das 4 fronteiras ativas realmente possui a responsabilidade.
2. Atualizar primeiro a fonte principal do contrato e depois as skills consumidoras.
3. Revisar discovery para garantir que o pedido correto aciona a skill correta.
4. Rodar a validação de skills e a validação agregada de governança.
5. Corrigir drift documental antes de concluir.

## Validação Automatizada

- `Tools/Test-SkillsGovernance.ps1` valida local canônico, frontmatter, seções obrigatórias, placeholders, referências cruzadas, consistência da taxonomia ativa, espelhamento em `.gemini/skills/` e presença dos mirrors globais obrigatórios do Codex.
- `Tools/Test-SourceEncoding.ps1` valida a política de encoding de fontes e documentação, incluindo `.md`, `.py`, `.js`, `.json`, `.txt`, `.sql`, `.html` e `.css` em UTF-8 sem BOM e `.ps1`/`.psm1` em UTF-8 with BOM.
- `Tools/ValidarAutomacoes.ps1 -OnlyGovernance` agrega a governança de skills com os checks nativos do repositório.
- A task recomendada no workspace para revisão rápida continua sendo `Validacao: Skills`.
