---
name: ai-native-development-standard
description: Use when updating repository context, maintaining skills, aligning code with documentation, or deciding how AI-native governance should be reflected across README, CONTEXT, SECURITY, GEMINI, and CHANGELOG artifacts.
---

## Purpose
Definir como o workspace deve ser descrito para agentes, como o contexto local deve permanecer sincronizado com o codigo e como as skills devem evoluir sem gerar descoberta ambigua ou documentacao ornamental.

## When to Use
- Use ao criar, revisar ou reescrever qualquer `SKILL.md` em `.github/skills`.
- Use ao atualizar `README.md`, `CONTEXT.md`, `SECURITY.md`, `GEMINI.md`, `CHANGELOG.md` ou `docs/ai-native-context-monitor.md` apos mudancas estruturais no hub.
- Use ao decidir se uma regra deve viver em uma skill, em `references/` da skill ou em documentacao raiz do repositorio.
- Use ao corrigir drift entre implementacao real e o que a documentacao afirma sobre stack, governanca ou ownership.

## Do Not Use When
- Nao use para definir contratos de runtime, `ExecId`, idempotencia ou handoff entre linguagens; nesses casos use `enterprise-orchestration-contract`.
- Nao use para regras de seguranca, logs, segredos ou encoding; nesses casos use `automation-runtime-safety`.
- Nao use para detalhe de PowerShell, Node.js ou HTML/CSS; nesses casos use a skill especializada do runtime ou canal.

## Related Skills
- `enterprise-orchestration-contract` para contratos transversais do fluxo de execucao.
- `automation-runtime-safety` para guardrails operacionais e seguranca.
- `powershell-automation-monitor` quando a governanca documental depender de padroes especificos de scripts ou modulos PowerShell.

## Non-Negotiable Rules
- Mantenha o frontmatter de skill restrito aos campos suportados pelo sistema: `name`, `description`, `argument-hint`, `user-invocable` e `disable-model-invocation`.
- Escreva `description` iniciando com `Use when` e deixando explicito quando a skill deve ser escolhida em vez de outra skill parecida.
- Reescreva documentacao quando o codigo real mudar; nao use o repositorio como vitrine institucional desconectada da implementacao.
- Atualize `CHANGELOG.md` quando a mudanca alterar comportamento, contratos de governanca, taxonomia de skills ou fluxo de operacao do hub.
- Prefira melhorar uma skill existente antes de criar outra. Crie nova skill apenas quando existir um fluxo recorrente, especializado e com fronteira propria.

## Repo-Specific Constraints
- Leia `README.md` para visao geral e estado do hub antes de alterar documentacao estrutural.
- Leia `CONTEXT.md` quando a mudanca tocar regras de negocio, automacoes fiscais ou contratos operacionais entre componentes.
- Leia `SECURITY.md` quando a mudanca tocar dados sensiveis, logs, credenciais ou protecao de dados.
- Leia `GEMINI.md` quando a mudanca tocar encoding, bootstrap local, skills ou politicas locais de edicao.
- Leia `docs/ai-native-context-monitor.md` quando a mudanca tocar estado operacional recente, arquitetura, governanca ou contratos que futuros agentes precisam conhecer.
- Use `.github/skills/README.md` como fonte canonica da taxonomia ativa; nao reintroduza skills legadas nem referencias a stack anterior.

## Validation
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SkillsGovernance.ps1 -BasePath .` apos alterar qualquer skill ou o README de skills.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` quando a mudanca afetar governanca do workspace como um todo.
- Revise manualmente se `README.md`, `CONTEXT.md`, `SECURITY.md`, `GEMINI.md`, `CHANGELOG.md` e `docs/ai-native-context-monitor.md` continuam coerentes entre si e com os arquivos em `Infrastructure/`, `Orchestrator/` e `lib/`.

## Troubleshooting
- Se duas skills parecerem competir pelo mesmo pedido, refine primeiro `description`, `Do Not Use When` e `Related Skills` em vez de duplicar regras.
- Se a documentacao afirmar algo que nao existe mais no repositorio, trate como drift e corrija a fonte canonica antes de ajustar referencias secundarias.
- Se o validador acusar taxonomia invalida, compare `.github/skills/README.md` com as pastas reais em `.github/skills`.

## Pre-Delivery Checklist
- Confirme que a mudanca documental reflete o estado atual do codigo.
- Confirme que nao ha mencao ativa a skills legadas ou stacks descontinuadas.
- Confirme que `description`, `Do Not Use When` e `Related Skills` permitem discovery claro.
- Confirme que `CHANGELOG.md` foi atualizado quando a mudanca alterou comportamento ou governanca.
