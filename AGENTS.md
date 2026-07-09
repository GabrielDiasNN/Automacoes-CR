# Unified Agent Contract

Este repositório é compartilhado entre ChatGPT/Codex, Gemini CLI, Antigravity e outros agentes locais.

O objetivo deste contrato é fazer com que os agentes trabalhem em equipe, com a mesma hierarquia de contexto, as mesmas regras de edição e a mesma governança de skills.

## Ordem de Precedência

Quando houver conflito entre instruções, use esta ordem:

1. Instruções explícitas do usuário para a tarefa atual.
2. Regras nativas do runtime do agente.
3. Contratos locais do repositório:
   - `AGENTS.md`
   - `CLAUDE.md`
   - `GEMINI.md`
   - `README.md`
   - `CONTEXT.md`
   - `SECURITY.md`
4. Skills canônicas do workspace em `.github/skills/`.
5. Diretrizes globais compartilhadas da máquina:
   - `%USERPROFILE%\.gemini\GEMINI.md`
   - `%USERPROFILE%\.gemini\antigravity\skills\`
   - `%USERPROFILE%\.codex\skills\`
6. Espelhos de compatibilidade.

Regra de resolução:

- Em conflito entre regra local do repositório e regra global da máquina, vence a regra local do repositório.
- Em conflito entre fonte canônica e mirror, vence sempre a fonte canônica.
- Em conflito entre simplicidade de código (princípio comportamental) e exigência de governança/documentação: governança prevalece para arquivos de infraestrutura, configuração e contratos; simplicidade prevalece para código de produto e lógica de negócio.

## Bootstrap Obrigatório

Antes de análise profunda, refatoração estrutural, mudança de skill ou alteração de governança:

1. Ler `AGENTS.md`.
2. Ler `CLAUDE.md` quando a tarefa tocar qualidade de código, design de solução ou comportamento de agente.
3. Ler `README.md`, `CONTEXT.md` e `SECURITY.md`.
4. Ler `GEMINI.md` do repositório quando a tarefa tocar contexto AI-Native, encoding, documentação ou políticas locais.
5. Ler `.github/skills/README.md` e depois a skill aplicável quando a tarefa tocar governança, runtime, orquestração, UI ou canais.
6. Se o agente estiver rodando fora do ecossistema Codex, tratar `.gemini/skills/` apenas como alias de `.github/skills/`.
7. Se a tarefa envolver diretrizes globais compartilhadas entre agentes, ler também `%USERPROFILE%\.gemini\GEMINI.md` e as skills globais aplicáveis.

## Idioma e Comunicação

- Toda comunicação com o usuário deve ser em Português do Brasil.
- Mensagens de commit, ADRs, changelog técnico e instruções operacionais devem permanecer em Português do Brasil.
- O tom deve ser técnico, direto e auditável.

## Princípios Comportamentais

Estes princípios se aplicam a todos os agentes e devem guiar cada decisão de implementação.

**1. Pensar Antes de Executar**

Antes de implementar qualquer mudança:
- Declare assunções explicitamente. Se incerto, pergunte.
- Se existirem múltiplas interpretações, apresente-as — não escolha silenciosamente.
- Se existir abordagem mais simples, diga. Questione quando pertinente.
- Se algo não estiver claro, pare. Nomeie o que está confuso. Pergunte.

**2. Simplicidade Primeiro**

- Sem features além do que foi pedido.
- Sem abstrações para código de uso único.
- Sem tratamento de erro para cenários impossíveis.
- Se você escrever 200 linhas e poderiam ser 50, reescreva.

**3. Mudanças Cirúrgicas**

- Toque apenas o necessário; não "melhore" código, comentários ou formatação adjacentes.
- Siga o estilo existente do arquivo.
- Se notar código morto não relacionado, mencione — não delete sem pedido.
- Cada linha alterada deve ser rastreável diretamente ao pedido do usuário.

**4. Execução Orientada a Metas**

- Transforme tarefas em metas verificáveis antes de iniciar.
- Para tarefas de múltiplos passos, declare um plano e verifique cada etapa.
- Critérios fracos ("fazer funcionar") exigem clarificação; declare critérios de sucesso precisos.

## Regras de Encoding

- Arquivos PowerShell (`.ps1`, `.psm1`) devem usar `UTF-8 with BOM`.
- Arquivos Markdown (`.md`) devem usar `UTF-8` sem BOM, com acentuação normal em PT-BR quando o texto estiver em português.
- Arquivos `.py`, `.js`, `.json`, `.txt`, `.sql`, `.html` e `.css` devem usar `UTF-8` sem BOM, salvo exceção explícita do repositório.
- Antes de salvar, o agente deve verificar se a mudança preserva o encoding esperado e não introduz mojibake ou perda de acentuação em documentação Markdown.

## Fonte Canônica de Skills do Repositório

- A fonte canônica das skills do workspace é `.github/skills/`.
- O diretório `.gemini/skills/` existe apenas como espelho de compatibilidade para Gemini CLI e ferramentas relacionadas.
- Cada item em `.gemini/skills/` deve apontar para a skill correspondente em `.github/skills/`.
- Não manter duas cópias editáveis da mesma skill do workspace.

## Fonte Canônica de Skills Globais Compartilhadas

- As skills globais compartilhadas entre Gemini CLI, Antigravity e Codex devem ter fonte única na máquina.
- A fonte canônica atual das skills globais compartilhadas é `%USERPROFILE%\.gemini\antigravity\skills\`.
- As exposições em outros agentes, incluindo `%USERPROFILE%\.codex\skills\`, devem ser mirrors por junction/symlink sempre que possível.
- Não manter cópias editáveis divergentes da mesma skill global em múltiplos diretórios.

Skills globais compartilhadas obrigatórias:

- `ai-engineering-discipline`
- `protocolo-valeg`
- `git-ide-governance-skill`

`ai-engineering-discipline` define a disciplina global de engenharia com IA: contexto correto, menor mudança suficiente, simplicidade, depuração verificável e separação entre protótipo e produção. Ela não substitui `protocolo-valeg` nem `git-ide-governance-skill`; mudanças envolvendo Git devem continuar usando a skill de Git.

## Regra Operacional para Skills

- Ao alterar skill do workspace, editar somente `.github/skills/`.
- Ao alterar skill global compartilhada, editar somente a fonte canônica em `%USERPROFILE%\.gemini\antigravity\skills\`.
- Preservar mirrors como link simbólico ou junction para evitar drift.
- Se um agente descobrir a skill via mirror, ele deve tratar o conteúdo como alias da fonte canônica.
- Melhorar skill existente antes de propor skill nova.

## Contrato Compartilhado Entre Agentes

Todos os agentes devem operar com estas regras não negociáveis:

- Ler o contexto central antes de propor mudança estrutural.
- Atualizar documentação viva quando a implementação mudar de forma relevante.
- Manter idempotência, cleanup, tratamento de erro, observabilidade e Zero Trust.
- Não expor segredos em logs, comandos, mensagens ou exemplos.
- Não sobrescrever nem reverter mudanças de outro agente sem instrução explícita.
- Se encontrar worktree sujo ou conflito real de ownership, trabalhar em volta do conflito ou pedir orientação.
- Preferir diffs pequenos, reversíveis e auditáveis.

## Governança de Git e IDE

- Operações Git devem ser seguras por padrão.
- Antes de comando mutável relevante, inspecionar estado com comandos como `git status`, `git log` ou `git reflog`, conforme o caso.
- Não recomendar nem executar `git reset --hard`, `git checkout --`, `git push --force` ou equivalente destrutivo sem pedido explícito do usuário e aviso claro de impacto.
- Commits devem ser atômicos, com mensagem clara e contexto suficiente para auditoria.

## Colaboração com Documentação AI-Native

- `README.md` deve refletir objetivo, setup e estado geral.
- `CONTEXT.md` deve refletir regras de negócio, fluxos, contratos e integrações.
- `SECURITY.md` deve refletir guardrails e tratamento de dados sensíveis.
- `CHANGELOG.md` deve ser atualizado quando a mudança alterar comportamento, governança, arquitetura ou contrato operacional.

## Descoberta Recomendada

- ChatGPT/Codex: ler primeiro `.github/skills/README.md` e depois a skill aplicável.
- Gemini CLI e Antigravity: podem ler `.gemini/skills/`, mas o conteúdo esperado é o mesmo de `.github/skills/`.
- Claude Code: além de `CLAUDE.md`, usa `.claude/agents/` (subagentes especializados), `.claude/skills/` (skills locais) e `.claude/settings.json` (hooks/config); GitHub Copilot usa `.github/copilot-instructions.md` como fonte de instruções.
- Para regras globais compartilhadas entre agentes, carregar `%USERPROFILE%\.gemini\GEMINI.md` e as skills globais canônicas.
- Quando houver divergência entre `.github/skills/` e `.gemini/skills/`, considerar `.github/skills/` a fonte de verdade do workspace.

## Validação

- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SkillsGovernance.ps1 -BasePath .`.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SourceEncoding.ps1 -RootPath .`.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` quando a mudança tocar governança mais ampla.
- Para mudanças de Dashboard/UI, rotas FastAPI consumidas pela UI, fluxos operacionais E2E ou contrato de interação front-back:
  - A validação final obrigatória deve ser E2E com Playwright.
  - O método padrão é validar a tela real servida em `http://127.0.0.1:8000/dashboard/`, incluindo navegação, ações críticas e ausência de erros de console.
  - Essa validação deve acontecer por último, após testes de governança, e deve ser registrada na entrega técnica.
- O validador deve manter a taxonomia em `.github/skills/`, o espelho em `.gemini/skills/`, os mirrors globais obrigatórios do Codex e a política de encoding de `.md`, `.py`, `.js`, `.json`, `.txt`, `.sql`, `.html`, `.css`, `.ps1` e `.psm1` consistentes.
