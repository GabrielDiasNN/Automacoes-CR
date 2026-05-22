# Governança de Contexto: Projeto Automacoes

## Mandatos de Encoding

Estas regras são obrigatórias para todos os agentes e ferramentas que editam este repositório:

1. **PowerShell (`.ps1`, `.psm1`)**: salvar como `UTF-8 with BOM`.
2. **Demais arquivos textuais (`.md`, `.py`, `.js`, `.json`, `.txt`, `.sql`, `.html`, `.css`)**: salvar como `UTF-8` sem BOM, salvo exceção explícita do repositório.
3. **Markdown em PT-BR**: preservar acentuação normal; não usar ASCII empobrecido e não introduzir mojibake.
4. **Validação**: antes de concluir mudanças documentais ou de governança, rodar os validadores aplicáveis de encoding e governança.

## Propósito do Contexto Local

Este arquivo é o contrato local de bootstrap para Gemini CLI e Antigravity dentro do Hub de Automações. Ele deve permanecer curto, normativo e estável.

O histórico operacional e os marcos recentes do contexto AI-Native vivem em `docs/ai-native-context-monitor.md`. O histórico completo de versões permanece em `CHANGELOG.md`.

## Protocolo Específico do Projeto

1. **Contexto AI-Native**: ao iniciar tarefas no Hub, leia `README.md`, `CONTEXT.md`, `SECURITY.md` e, quando a tarefa depender de estado recente, `docs/ai-native-context-monitor.md`.
2. **Documentação viva**: atualize a documentação impactada quando a implementação alterar arquitetura, contrato operacional, governança, segurança, regra de negócio ou validação obrigatória.
3. **Histórico de mudanças**: atualize `CHANGELOG.md` quando a mudança alterar comportamento, governança, arquitetura ou contrato operacional.
4. **Monitor AI-Native**: atualize `docs/ai-native-context-monitor.md` quando a mudança alterar o estado operacional que futuros agentes precisam conhecer para decidir corretamente.
5. **Hierarquia local**:
   - `README.md`: visão geral e estado geral do hub.
   - `CONTEXT.md`: regras de negócio, fluxos, contratos e integrações.
   - `SECURITY.md`: guardrails e tratamento de dados sensíveis.
   - `CHANGELOG.md`: histórico completo e auditável de versões.
   - `docs/ai-native-context-monitor.md`: snapshot curado para bootstrap de agentes.
6. **Skills compartilhadas**: use `.github/skills/` como fonte canônica das skills. O diretório `.gemini/skills/` existe apenas como espelho de compatibilidade para Gemini CLI e Antigravity.
7. **Disciplina global de engenharia com IA**: herdar a skill global `ai-engineering-discipline`; regras locais deste repositório continuam prevalecendo quando houver conflito.
8. **Validação E2E final com Playwright**: para mudanças em UI/SPA/dashboard, rotas FastAPI consumidas pela UI, fluxos operacionais E2E ou contrato front-back, a validação final obrigatória deve ser Playwright E2E por último, conforme `docs/playwright-e2e-standard.md`.

## Checklist Local

- [ ] `README.md`, `CONTEXT.md` e `SECURITY.md` permanecem coerentes com a mudança?
- [ ] `CHANGELOG.md` foi atualizado quando houve mudança de comportamento, governança, arquitetura ou contrato?
- [ ] `docs/ai-native-context-monitor.md` foi atualizado quando houve mudança de estado operacional relevante para agentes?
- [ ] A política de encoding foi preservada?
- [ ] O tom técnico em Português do Brasil foi mantido?
