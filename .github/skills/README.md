# Skills Canônicas do Repositório

Este diretório é a fonte canônica das **skills de padrão** do workspace: as 7 normas escritas que governam decisões de implementação. Ele não contém as skills operacionais executáveis do projeto — essas vivem em `.claude/skills/` (ver a seção abaixo).

O projeto atual é 100% nativo, com stack consolidada em Python, PowerShell e Node.js. Skills legadas de migração para Python ou de runtime VBA não fazem mais parte da taxonomia ativa e não devem ser reintroduzidas em discovery, `Related Skills` ou documentação operacional.

## Regra Oficial

- Local canônico das skills de padrão: `.github/skills` — **a única árvore editável** para norma escrita.
- Mirror declarado delas: `.gemini/skills` (junctions para `.github/skills`, consumido pelo Gemini CLI e pelo Antigravity).
- Fonte única das skills operacionais do projeto: `.claude/skills` — **a única árvore editável** para comando/driver executável.
- Mirror declarado delas: `.agents/skills` (junctions para `.claude/skills`, consumido por Codex/Antigravity).
- Não manter skills duplicadas em múltiplos diretórios para evitar drift: mirror é link, nunca cópia — `Tools/Test-SkillsGovernance.ps1` reprova cópia real, alvo divergente e mirror órfão.
- Mirror não é versionado (ver `.gitignore`): é artefato local, recriado por `pwsh -File Tools\New-SkillMirrors.ps1`. Rode-o após clonar o repositório e sempre que criar ou renomear uma skill — skill nova sem espelho reprova a governança com `GEMINI_SKILL_MIRROR_MISSING` (skills de padrão em `.github/skills`) ou `AGENTS_SKILL_MIRROR_MISSING` (skills operacionais em `.claude/skills`, cobrado apenas quando `.agents/skills` já existe — o mirror inteiro é opcional). Use `-Force` para substituir um mirror que virou cópia real.
- Melhorar skill existente antes de propor uma skill nova.

## Duas Árvores de Skills e Exposição por Junction

O repositório versiona **duas** árvores de skills, com propósitos, donos e validadores distintos:

| Árvore | Conteúdo | Editável? | Validador |
|---|---|---|---|
| `.github/skills/` | 7 skills de **padrão** (norma escrita, taxonomia ativa) | Sim — fonte canônica | `Tools/Test-SkillsGovernance.ps1` |
| `.claude/skills/` | skills **operacionais** executáveis do projeto: ci-gates, run-orchestrator, preflight, quality-gate, run-tests, new-automation (drivers e comandos) | Sim — fonte única | governança agregada de `ValidarAutomacoes.ps1` |
| `.gemini/skills/` | mirror por junction de `.github/skills/` | Não — alias | reprovado se cópia real |
| `.agents/skills/` | mirror por junction de `.claude/skills/` | Não — alias | reprovado se cópia real |

**Estado-alvo (mudança em andamento):** o Claude Code — o agente que mais trabalha neste repositório — carrega **somente** `.claude/skills`, nunca `.github/skills`. Para que ele enxergue as 7 skills de padrão, elas passam a ser expostas por junction em `.claude/skills/<nome>`. `.github/skills` continua sendo a **única** árvore editável dessas skills; o junction é apenas um alias de leitura. `Tools\New-SkillMirrors.ps1` cria esses junctions e o `.gitignore` os exclui do versionamento. Na prática: **editar skill de padrão = editar `.github/skills/`, sempre** — independentemente de qual agente a descobriu.

Qual árvore cada agente lê:

- **Claude Code** — lê só `.claude/skills/` (skills operacionais + junctions das skills de padrão).
- **Gemini CLI / Antigravity** — leem `.gemini/skills/` (espelho de `.github/skills/`) mais as regras locais em `.agents/rules/` e os contratos de raiz `AGENTS.md` / `GEMINI.md`.
- **Codex / ChatGPT** — leem primeiro `.github/skills/README.md`, depois a skill de padrão aplicável; as operacionais chegam via `.agents/skills/` (espelho de `.claude/skills/`).

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

A lista dos 7 nomes ativos também está hardcoded em `$script:ActiveSkillNames` (linha ~28 de `Tools/Test-SkillsGovernance.ps1`): adicionar uma 8a skill de padrão exige editar esse script **e** esta seção, senão a skill nova é tratada como fora da taxonomia (`ACTIVE_SKILL_MISSING_IN_README`).

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

Toda `SKILL.md` deve conter, no mínimo, estas seções em `##`, nesta ordem:

1. `Purpose`
2. `When to Use`
3. `Do Not Use When`
4. `Related Skills`
5. `Non-Negotiable Rules`
6. `Repo-Specific Constraints`
7. `Validation`
8. `Troubleshooting`
9. `Pre-Delivery Checklist`

Faltar uma seção gera `REQUIRED_SECTION_MISSING`; repetir gera `SECTION_DUPLICATED`. Seções extras são permitidas quando agregam decisão operacional real, não texto ornamental.

## Regras de Descoberta

- `description` deve começar com `Use when`.
- `description` deve diferenciar a skill de outra skill próxima.
- `Do Not Use When` é obrigatória para reduzir overlap e deve citar a skill rival pelo nome.
- `Related Skills` deve citar apenas skills existentes na taxonomia ativa (as 7 acima); qualquer outro token entre crases nessa seção vira `RELATED_SKILL_INVALID`.
- Regras transversais devem ter fonte única; skills consumidoras devem referenciar nomeando arquivo **e** seção, não duplicar. Encoding é `AGENTS.md § Regras de Encoding`; limites de mypy/pylint são `docs/governance-contracts.md § Contrato Python — mypy \`--strict\`` e `§ Contrato Python — pylint`; escopo do lint bloqueante do CI é a skill operacional em `.claude/skills/ci-gates/SKILL.md`.

## Regras de Governança

1. Criar ou alterar skill de padrão sempre em `.github/skills`; criar ou alterar skill operacional sempre em `.claude/skills`.
2. Bloquear placeholders como `Conforme diretrizes globais.`.
3. Não citar skills legadas ou inexistentes em `Related Skills` ou na taxonomia; as skills legadas de migração Oracle e de runtime VBA (fixadas em `$script:LegacySkillNames` de `Tools/Test-SkillsGovernance.ps1`) continuam banidas em toda a documentação.
4. Referenciar artefatos reais do repositório nas seções operacionais sempre que a regra depender da implementação local.
5. Manter `README.md`, `CONTEXT.md`, `SECURITY.md`, `GEMINI.md` e `CHANGELOG.md` coerentes com a stack atual quando a mudança tocar governança. `CHANGELOG.md` segue Keep-a-Changelog (cabeçalho `## [x.y.z] - DD/MM/AAAA` no topo).
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
4. Se criou ou renomeou skill, rodar `pwsh -File Tools\New-SkillMirrors.ps1` para recriar os junctions dos mirrors.
5. Rodar a validação de skills e a validação agregada de governança.
6. Corrigir drift documental antes de concluir.

## Validação Automatizada

- `Tools/Test-SkillsGovernance.ps1` valida local canônico, frontmatter, seções obrigatórias, placeholders, referências cruzadas de `Related Skills`, consistência da taxonomia ativa, espelhamento em `.gemini/skills/` e `.agents/skills/` e presença dos mirrors globais obrigatórios do Codex. Rode com o caminho real, nunca com forma 8.3 (`C:\Users\GABRIE~1.DIA\...`): o alvo da junction volta expandido e produz falso `*_MIRROR_TARGET_INVALID`.
- `Tools/Test-SourceEncoding.ps1` valida a política de encoding de fontes e documentação por extensão. O contrato de qual extensão leva BOM não se repete aqui: fonte única em `AGENTS.md § Regras de Encoding`.
- `Tools/ValidarAutomacoes.ps1 -OnlyGovernance` agrega a governança de skills com os checks nativos do repositório.
- A task recomendada no workspace para revisão rápida continua sendo `Validacao: Skills`.
