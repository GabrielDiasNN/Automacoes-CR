# Unified Agent Contract

Contrato compartilhado entre ChatGPT/Codex, Gemini CLI, Antigravity e Claude Code para manter mesma hierarquia de contexto, regras de edição e governança.

## Precedência

1. Instrução explícita do usuário na tarefa atual.
2. Regras nativas e de segurança do runtime.
3. Contratos locais: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `README.md`, `CONTEXT.md`, `SECURITY.md`, `.agents/rules/`.
4. Skills canônicas do workspace em `.github/skills/`.
5. Diretrizes globais (`%USERPROFILE%\.gemini\GEMINI.md`, `%USERPROFILE%\.gemini\antigravity\skills\`, `%USERPROFILE%\.codex\skills\`).
6. Mirrors de compatibilidade.

Conflito local vs. global → vence a **regra local**. Canônica vs. mirror → vence a **fonte canônica**. Simplicidade de código vs. governança/documentação → governança vence em infraestrutura/config/contratos; simplicidade vence em código de produto.

## Contexto Progressivo (Bootstrap sob Demanda)

Evite carregar toda a documentação do hub em tarefas simples. Leia apenas o que a frente exige:

- **Sempre ativo:** este `AGENTS.md` (e `CLAUDE.md` / `GEMINI.md` conforme o agente).
- **Sob demanda:** `README.md`, `CONTEXT.md` (baseline v1.0.0; histórico antigo em `docs/historico/CONTEXT-history.md`), `SECURITY.md`, `docs/ai-native-context-monitor.md` (estado e armadilhas recentes) e `.github/skills/README.md` quando tocar arquitetura, governança, segurança ou skills.
- **Subsistema:** `CLAUDE.md` de subpasta (`Orchestrator/`, `Dashboard/`, `Produção Beneficimento/`, `lib/`) e `.agents/rules/`.
- **Logs de versão:** nunca leia `CHANGELOG.md` inteiro (~52k tokens); use busca por termo/versão ou trecho final.

## Idioma, Princípios e Encoding

- **Idioma:** Português do Brasil em toda comunicação, commits, ADRs e documentação operacional; tom técnico e auditável.
- **Princípios Comportamentais:** fonte única em `karpathy-guidelines` (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution; ver `CLAUDE.md`).
- **Encoding:** `.ps1`/`.psm1` em `UTF-8 with BOM`; `.md`, `.py`, `.js`, `.json`, `.txt`, `.sql`, `.html`, `.css` em `UTF-8` sem BOM. Markdown em PT-BR deve preservar acentuação sem mojibake.

## Skills Canônicas e Descoberta

| Fonte canônica | Conteúdo | Editável? | Validador |
| :--- | :--- | :---: | :--- |
| `.github/skills/` | 9 skills de **padrão** | sim | `Tools/Test-SkillsGovernance.ps1` |
| `.claude/skills/` | 7 skills **operacionais** (`ci-gates`, `log-triage`, `preflight`, `quality-gate`, `run-tests`, `new-automation`, `run-orchestrator`) | sim | — |

- **Mirrors (não editáveis):** `.gemini/skills/` → `.github/skills/`; `.agents/skills/` → operacionais de `.claude/skills/`; `.claude/skills/<padrão>` → junctions para `.github/skills/`. Ao criar/renomear skill, rodar `pwsh -File Tools\New-SkillMirrors.ps1`.
- **Skills globais obrigatórias:** fonte única em `%USERPROFILE%\.gemini\antigravity\skills\` (`ai-engineering-discipline`, `protocolo-valeg`, `git-ide-governance-skill`).
- **App real:** para subir, autenticar no dashboard, capturar tela ou chamar `/api/*`, use `.claude/skills/run-orchestrator/` (checar `health` antes de reiniciar).

## Modo de Trabalho e Contrato Compartilhado

- **Autonomia e paradas:** prossiga sem perguntar quando não houver decisão; pare antes de apagar dados/arquivos, force-push, reset destrutivo, ações externas (push, PR, comentários) ou alterações fora do repo. Em tarefas longas use `TASKS.md` (ignorado no Git) e encerre com **Bloqueado em mim**, **Alterado**, **Encontrado**; marque o que não foi confirmado e onde procurou.
- **Dependências:** autorização permanente do dono para instalar pacotes dos locks/CI e módulos PS dos gates (fonte oficial, escopo de venv/usuário/contêiner — nunca fora do `.venv` na máquina de produção nem com credencial no comando; barreira de rede/classificador é parada, não contornar).
- **Subagentes e revisores:** edição paralela só em `worktree` com escopos disjuntos e revisão de diff/hash pelo principal. Diretrizes: usar `diretrizes-verifier` + `Tools/Test-AgentGuidelines.ps1`. Revisores em `.claude/agents/` são restritos a leitura (`changelog-reviewer` tem `Bash` só para `git diff` por instrução).
- **Engenharia:** manter idempotência, cleanup, tratamento de erro, observabilidade, Zero Trust, diffs pequenos e documentação viva atualizada (`README.md`, `CONTEXT.md`, `SECURITY.md`, `CHANGELOG.md`, `docs/ai-native-context-monitor.md`). Nunca expor segredos nem reverter trabalho alheio sem pedido explícito.

## Governança de Git e PR

- Inspecionar estado (`git status`, `git log`) antes de mutação; nunca executar `git reset --hard`, `git checkout --`, `git clean -fd` ou `git push --force` sem pedido explícito e aviso.
- **Fluxo autorizado (quando entrega por PR for solicitada — detalhe em `.agents/workflows/fluxo-pr-completo.md`):**
  1. **Commit:** stage seletivo, mensagem atômica em PT-BR (`[1.3.xxx]` se alterar `CHANGELOG.md`), respeitando `pre-commit` (nunca `--no-verify`). Se pedido só commit, parar aqui.
  2. **PR:** checar `gh auth status`, `git push -u origin <branch>` (nunca direto em `main`) e `gh pr create` com `.github/pull_request_template.md` e evidências reais.
  3. **CI:** monitorar checks (`gh pr checks <n>`, timers com `schedule` em vez de `sleep`); em falha, corrigir na branch, validar localmente e reenviar até 0 falhas.
  4. **Merge:** com checks 100% verdes e `MERGEABLE`/`CLEAN`, rodar `gh pr merge <n> --squash --delete-branch`, atualizar `main` (`git pull --ff-only`) e `git fetch --prune`. Parar se houver conflito ou falha persistente.

## Validação Obrigatória

- Governança e encoding: `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SkillsGovernance.ps1 -BasePath .`, `Tools/Test-SourceEncoding.ps1 -RootPath .` e `Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` (quando tocar governança ampla).
- **Dashboard/UI, rotas FastAPI da UI ou fluxos E2E:** validação final obrigatória em Playwright na URL real `http://127.0.0.1:8000/dashboard/` (navegação, ações críticas e console limpo), executada por último e registrada na entrega.
