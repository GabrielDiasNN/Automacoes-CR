# Padrão Oficial de Validação E2E com Playwright

Data de vigência: 17/05/2026

## Objetivo
Padronizar Playwright como validação E2E final para mudanças que afetem experiência operacional do Orchestrator.

## Quando é obrigatório
- Alterações em `Dashboard/` (`.html`, `.css`, `.js`).
- Alterações em endpoints FastAPI consumidos pela UI (`/api/system/*`, `/api/automations*`, `/api/executions*`, `/ws/*`).
- Ajustes de fluxos operacionais de execução, logs, filtros, ações globais ou autenticação da SPA.

## Ordem de validação
1. Validadores de governança (`Test-SourceEncoding`, `ValidarAutomacoes`, etc.).
2. Testes de contrato/backend aplicáveis (`pytest`, integridade de API).
3. **Última etapa obrigatória:** validação E2E com Playwright.

## Método padrão (fonte de verdade)
- URL alvo: `http://127.0.0.1:8000/dashboard/`.
- Validar página real servida pelo Orchestrator, não apenas HTML estático.
- Ferramenta de apoio: `.claude/skills/run-orchestrator/driver.py` (comando `smoke`) autentica,
  navega as seis rotas e coleta erros de console. Ele **não** substitui a evidência formal desta
  seção — cobre navegação e console, não os fluxos de filtro e log abaixo.
- Itens mínimos de aceite:
  - Navegação entre os módulos reais da SPA: `Painel`, `Execuções`, `Monitor`, `Beneficiamento`,
    `Automações`, `Sistema` (a rota `/observabilidade` é redirect preservado para `/monitor`).
  - Fluxo de `Execuções`: carregar listagem e aplicar ao menos um filtro.
  - Fluxo de logs: abrir modal de logs para uma execução.
  - Console limpo: zero erros de console no fluxo validado.
  - Indicador de conexão da API refletindo estado real (`ONLINE/OFFLINE`).

## Evidência obrigatória na entrega
- Informar que a validação E2E Playwright foi executada por último.
- Registrar:
  - URL validada;
  - módulos navegados;
  - ações críticas testadas;
  - status de erros de console.
- Use o template oficial: `docs/playwright-e2e-evidence-template.md`.
- A evidência gerada pode existir apenas localmente ou na pipeline; o repositório versiona o padrão e o template, não um relatório gerado fixo.
- Quando houver documento de evidência gerado, ele deve passar em `Tools/Test-PlaywrightEvidence.ps1`.

## Diretriz para agentes de IA
- Em tarefas cobertas por este padrão, agentes devem considerar a entrega incompleta sem a etapa final Playwright E2E.
- Se Playwright não estiver disponível no ambiente, o bloqueio deve ser explicitado e tratado como pendência técnica de validação final.
