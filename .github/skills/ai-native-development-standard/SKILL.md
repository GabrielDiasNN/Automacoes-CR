---
name: ai-native-development-standard
description: Use when creating or editing any SKILL.md under .github/skills, the skills README, or the repo context files (README, CONTEXT, SECURITY, GEMINI, CHANGELOG, docs/ai-native-context-monitor.md), and when deciding whether a rule belongs in a skill, in a skill's references/, or in root documentation. Not for runtime, orchestration or security contracts.
---

## Purpose
Definir como as skills de padrão e a documentação de contexto do hub são escritas para agentes: onde cada regra vive (skill, `references/` da skill ou doc de raiz), como o contexto local não pode divergir do código, e como uma skill nova ou alterada mantém discovery sem ambiguidade. Alvo de densidade: cada regra abaixo muda uma decisão concreta e cita um artefato real do repositório.

## When to Use
- Ao criar, revisar ou reescrever qualquer `SKILL.md` em `.github/skills/` ou o `.github/skills/README.md`.
- Ao atualizar `README.md`, `CONTEXT.md`, `SECURITY.md`, `GEMINI.md`, `CHANGELOG.md` ou `docs/ai-native-context-monitor.md` depois de uma mudança estrutural no hub (stack, governança, taxonomia de skills, ownership).
- Ao decidir se um conteúdo novo vira skill, entra em `references/` de uma skill existente ou vai para doc de raiz.
- Ao corrigir drift: a documentação afirma algo sobre stack, contrato ou ownership que o código em `Orchestrator/`, `Infrastructure/` ou `lib/` não sustenta mais.
- Ao adicionar, renomear ou remover uma skill de padrão — o que inclui editar `Tools/Test-SkillsGovernance.ps1` e recriar mirrors.

## Do Not Use When
- Contrato de execução — `ExecId`, idempotência, estados, entrypoints, handoff PowerShell/Python: use `enterprise-orchestration-contract`.
- Zero Trust, logs, severidade, segredos, falha segura e a fonte única de encoding: use `automation-runtime-safety`.
- Detalhe de script, monitor ou módulo PowerShell: use `powershell-automation-monitor`.
- Backend Python, tipagem estrita, Pydantic, limites de mypy/pylint: use `python-enterprise-standard`.
- WhatsApp, headless, bootstrap `.bat`/`.cmd`: use `nodejs-communications`.
- Dashboard, HTML corporativo, assets de UI: use `html-css-enterprise-standard`.

## Related Skills
- `enterprise-orchestration-contract` — fonte dos contratos transversais de execução que as skills consumidoras referenciam em vez de redefinir.
- `automation-runtime-safety` — fonte única de encoding, Zero Trust e severidade; esta skill apenas aponta para lá.
- `python-enterprise-standard` e `powershell-automation-monitor` — quando a mudança documental depende de um padrão concreto de runtime, alinhe a doc com a skill do runtime antes.

## Non-Negotiable Rules
- Skill de padrão se edita **só** em `.github/skills/<nome>/SKILL.md`. Nunca em `.gemini/skills/`, `.agents/skills/` nem no alias que passará a existir em `.claude/skills/<nome>`: são mirrors por junction recriados por `Tools/New-SkillMirrors.ps1`, e `Tools/Test-SkillsGovernance.ps1` reprova cópia real (`GEMINI_SKILL_MIRROR_NOT_LINKED`), alvo divergente e mirror órfão.
- Frontmatter de skill só aceita as chaves de `$script:AllowedFrontmatterKeys` em `Tools/Test-SkillsGovernance.ps1`: `name`, `description`, `argument-hint`, `user-invocable`, `disable-model-invocation`. `name` tem de ser idêntico ao nome da pasta (`NAME_FOLDER_MISMATCH`); `description` tem de começar com `Use when` (`DESCRIPTION_DISCOVERY_INVALID`) e dizer quando escolher esta skill em vez de uma vizinha. Ownership, exemplo ou detalhe operacional vão para o corpo ou para `references/`.
- Preserve as 9 seções `##` de `$script:RequiredSections`, nesta ordem: `Purpose`, `When to Use`, `Do Not Use When`, `Related Skills`, `Non-Negotiable Rules`, `Repo-Specific Constraints`, `Validation`, `Troubleshooting`, `Pre-Delivery Checklist`. Faltar uma gera `REQUIRED_SECTION_MISSING`; repetir gera `SECTION_DUPLICATED`. Seção `##` extra só entra se carregar decisão real.
- `Related Skills` só pode nomear, entre crases, as 7 skills de `$script:ActiveSkillNames`: `ai-native-development-standard`, `automation-runtime-safety`, `enterprise-orchestration-contract`, `html-css-enterprise-standard`, `nodejs-communications`, `powershell-automation-monitor`, `python-enterprise-standard`. Qualquer outro token entre crases nessa seção vira `RELATED_SKILL_INVALID`. As skills legadas listadas em `$script:LegacySkillNames` (migração Oracle e runtime VBA) estão banidas em toda a documentação.
- Regra transversal não se reescreve aqui: delega nomeando arquivo **e** seção. Encoding vai para `AGENTS.md § Regras de Encoding` (fonte única canônica; `GEMINI.md` apenas resume, não cite como fonte primária). Limites exatos de mypy `--strict` e pylint vão para `docs/governance-contracts.md § Contrato Python — mypy \`--strict\`` e `§ Contrato Python — pylint`. Escopo do lint bloqueante do CI vai para a skill `ci-gates` (`.claude/skills/ci-gates/SKILL.md`). O placeholder de texto vazio barrado por `PLACEHOLDER_CONTENT_DETECTED` em `Tools/Test-SkillsGovernance.ps1` é proibido.
- Atualize `CHANGELOG.md` (formato Keep-a-Changelog, cabeçalho `## [x.y.z] - DD/MM/AAAA` no topo) quando a mudança alterar comportamento, contrato de governança, taxonomia de skills ou fluxo de operação do hub. `Tools/Test-SemanticGovernance.ps1` reprova drift entre monitor, constantes, docs, skills e catálogo — reescreva a documentação junto com o código, não depois.
- Melhore uma skill existente antes de criar outra. Skill nova exige fluxo recorrente, especializado, com fronteira própria que não cabe nas 7 atuais nem em `references/` — e não ser apenas um problema de discovery resolvível via `description`/`Do Not Use When`/`Related Skills`.

## Repo-Specific Constraints
- Existem **duas** árvores de skills versionadas, com donos e validadores diferentes. `.github/skills/` = 7 skills de padrão (norma escrita), governadas por `Tools/Test-SkillsGovernance.ps1`. `.claude/skills/` = skills operacionais executáveis do projeto (ci-gates, run-orchestrator, preflight, quality-gate, run-tests, new-automation), com driver e comandos. Norma escrita vai para a primeira; comando executável vai para a segunda.
- Os mirrors não são versionados (`.gitignore`, regras `.agents/skills/` e `.gemini/*`): `.gemini/skills` espelha `.github/skills` (Gemini CLI), `.agents/skills` espelha `.claude/skills` (Codex/Antigravity). Recrie com `pwsh -File Tools/New-SkillMirrors.ps1` depois de clonar ou de criar/renomear uma skill — skill nova sem espelho reprova a governança (`GEMINI_SKILL_MIRROR_MISSING`; `AGENTS_SKILL_MIRROR_MISSING` só quando `.agents/skills` já existe, porque o mirror inteiro é opcional).
- Estado-alvo (mudança em andamento): as 7 skills de `.github/skills` passam a ser expostas ao Claude Code por junction em `.claude/skills/<nome>`, porque o Claude Code lê somente `.claude/skills`. `.github/skills` continua sendo a ÚNICA árvore editável; o junction é alias. `Tools/New-SkillMirrors.ps1` cria esses junctions e `.gitignore` os exclui do versionamento. Consequência prática: editar skill de padrão = editar `.github/skills/`, sempre.
- Qual árvore cada agente lê: Claude Code lê só `.claude/skills/` (daí o junction das skills de padrão). Gemini CLI e Antigravity leem `.gemini/skills/` (espelho de `.github/skills/`) mais `.agents/rules/`. Codex/ChatGPT leem primeiro `.github/skills/README.md`, depois a skill; `.agents/skills/` espelha `.claude/skills/` para eles.
- Adicionar uma 8a skill de padrão exige editar `Tools/Test-SkillsGovernance.ps1`: `$script:ActiveSkillNames` (linha ~28) está hardcoded e alimenta tanto a validação de `Related Skills` quanto a checagem `ACTIVE_SKILL_MISSING_IN_README`. Sem essa edição, a skill nova é tratada como fora da taxonomia.
- Antes de mexer em doc estrutural, leia: `README.md` (objetivo, setup, estado do hub), `CONTEXT.md` (regras de negócio, automações fiscais, ADRs 001-019), `SECURITY.md` (dados sensíveis, guardrails), `GEMINI.md` (encoding, bootstrap local, políticas locais de edição), `docs/ai-native-context-monitor.md` (estado operacional recente que futuros agentes precisam para decidir).
- `.github/skills/README.md` é a fonte canônica da taxonomia ativa: 7 skills em 4 fronteiras (Fundação / Contratos Transversais / Runtimes e Canais / Apresentação). Não reintroduza skill legada nem referência à stack anterior (migração Oracle, runtime VBA).

## Validation
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SkillsGovernance.ps1 -BasePath .` após qualquer edição em skill ou no README de skills. Exigência: 0 erro (WARN não bloqueia o exit, mas investigue cada um). Rode com o caminho real do repositorio, nunca com a forma curta 8.3 do Windows (nomes com `~1`): o alvo da junction volta sempre expandido e gera falso `*_MIRROR_TARGET_INVALID`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SourceEncoding.ps1 -RootPath .` — `.md` PT-BR precisa de acentuação completa; ASCII-ficação de palavra acentuada (`nao`, `codigo`, `sincronizacao`) é defeito. `Test-SkillsGovernance.ps1` sinaliza prosa sem acento com `SKILL_PTBR_ACCENTS_MISSING`.
- `pwsh -File Tools/New-SkillMirrors.ps1` quando adicionou ou renomeou uma skill; depois rode o `Test-SkillsGovernance.ps1` de novo.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` quando a mudança afeta governança do workspace inteiro.
- Revise à mão se `README.md`, `CONTEXT.md`, `SECURITY.md`, `GEMINI.md`, `CHANGELOG.md` e `docs/ai-native-context-monitor.md` continuam coerentes entre si e com `Infrastructure/`, `Orchestrator/` e `lib/`.

## Troubleshooting
| Sintoma | Causa / correção |
|---|---|
| `RELATED_SKILL_INVALID` | Bullet de `Related Skills` cita entre crases um nome fora das 7 de `$script:ActiveSkillNames`. Use só os nomes canônicos ou tire as crases. |
| `REQUIRED_SECTION_MISSING` / `SECTION_DUPLICATED` | As 9 seções `##` têm de aparecer exatamente uma vez, na ordem fixa. |
| `DESCRIPTION_DISCOVERY_INVALID` | `description` do frontmatter não começa com `Use when`. |
| `NAME_FOLDER_MISMATCH` | `name` do frontmatter difere do nome da pasta da skill. |
| `FRONTMATTER_KEY_NOT_ALLOWED` | Chave ad hoc no YAML. Só as 5 de `$script:AllowedFrontmatterKeys`. |
| `GEMINI_SKILL_MIRROR_MISSING` / `AGENTS_SKILL_MIRROR_*` | Rode `pwsh -File Tools/New-SkillMirrors.ps1` (`-Force` para trocar um mirror que virou cópia real). |
| `*_MIRROR_TARGET_INVALID` num ambiente onde os caminhos parecem certos | `-BasePath` recebeu caminho 8.3; rode com o caminho completo. |
| Skill nova (8a de padrão) reprovando mesmo com mirror criado | `$script:ActiveSkillNames` em `Tools/Test-SkillsGovernance.ps1` (linha ~28) é hardcoded; adicione o nome lá e em `.github/skills/README.md`. |
| Duas skills disputando o mesmo pedido | Refine `description`, `Do Not Use When` e `Related Skills` antes de dividir regra. |
| Doc afirma algo que não existe mais no repositório | Trate como drift: corrija a fonte canônica antes de ajustar referências secundárias. |

## Pre-Delivery Checklist
- `Tools/Test-SkillsGovernance.ps1 -BasePath .` retorna 0 erro (idealmente 0 warning).
- Arquivo em UTF-8 sem BOM, acentuação PT-BR intacta (`Tools/Test-SourceEncoding.ps1`).
- Editou só `.github/skills/`; mirror recriado se alguma skill foi adicionada ou renomeada.
- Frontmatter: `name` == pasta; `description` começa com `Use when`.
- As 9 seções `##` presentes e na ordem; nenhuma skill legada citada em lugar nenhum.
- Regra transversal delegada por arquivo + seção (`AGENTS.md § Regras de Encoding`, `docs/governance-contracts.md § Contrato Python — pylint`, skill `ci-gates`), não reescrita.
- `CHANGELOG.md` atualizado se comportamento, governança, taxonomia ou fluxo mudou.
- `README.md`, `CONTEXT.md`, `SECURITY.md`, `GEMINI.md` e `docs/ai-native-context-monitor.md` seguem coerentes entre si e com o código.
