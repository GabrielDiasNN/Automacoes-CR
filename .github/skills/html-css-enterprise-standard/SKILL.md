---
name: html-css-enterprise-standard
description: Use when changing dashboard templates, HTML reports, or enterprise-facing UI assets that must stay separated from business logic and remain compatible with the repository's dashboard contract and shared frontend assets.
---

## Purpose
Definir o contrato visual do hub para dashboards e saidas HTML, mantendo separacao entre apresentacao e regra de negocio, uso consistente de assets compartilhados e aderencia ao validador de template corporativo.

## When to Use
- Use ao alterar templates HTML em `.github/templates/`, `Dashboard/` ou relatorios gerados pelas automacoes.
- Use ao mexer em CSS, design tokens, funcoes de renderizacao de dashboard ou assets compartilhados em `lib/assets/`.
- Use ao revisar semantica, responsividade, acessibilidade ou legibilidade de interfaces renderizadas pelo hub.

## Do Not Use When
- Nao use para definir regras de negocio, calculos, filtros ou handoff de runtime; esses comportamentos devem permanecer fora do HTML.
- Nao use para contratos de orquestracao, `ExecId` ou arquivos de estado; nesses casos use `enterprise-orchestration-contract`.
- Nao use para politicas de seguranca, logs ou encoding; nesses casos use `automation-runtime-safety`.

## Related Skills
- `enterprise-orchestration-contract` quando a UI depender de dados produzidos pelo fluxo corporativo.
- `automation-runtime-safety` quando a saida HTML expuser logs, mensagens de erro ou texto sensivel.
- `nodejs-communications` se o HTML fizer parte de canal de comunicacao automatizada e nao apenas de dashboard.

## Non-Negotiable Rules
- Mantenha regra de negocio fora do template; HTML/CSS devem receber dados prontos para renderizacao.
- Reutilize assets compartilhados em `lib/assets/` antes de embutir bibliotecas ou fontes novas.
- Preserve semantica, responsividade e acessibilidade minima exigidas pelo contrato do dashboard.
- Nao reintroduza referencia conceitual a VBA; o estado atual do projeto e 100% nativo em Python, PowerShell e Node.js.
- Evite acoplamento visual com strings ou estruturas que so existam em uma automacao especifica sem necessidade clara.

## Repo-Specific Constraints
- Trate `.github/templates/dashboard-modern.html` como template canonico do dashboard moderno.
- Reutilize `lib/assets/css/fonts.css`, `lib/assets/js/apexcharts.min.js` e `lib/assets/js/lucide.min.js` quando o requisito ja estiver coberto por esses assets.
- Considere `Dashboard/dashboard.html` um output derivado; a fonte de contrato continua sendo o template e os dados JSON.
- Preserve placeholders e funcoes obrigatorias exigidos por `Tools/Test-DashboardTemplate.ps1`, incluindo `__DASHBOARD_JSON__`, `__REFRESH_SECONDS__` e funcoes de renderizacao.

## Validation
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-DashboardTemplate.ps1 -BasePath .`.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` se a mudanca tocar padroes globais de UI.
- Execute validacao E2E final com Playwright na interface servida em `http://127.0.0.1:8000/dashboard/`.
- A validacao Playwright deve ocorrer por ultimo e cobrir, no minimo:
  - navegacao entre modulos principais;
  - acao de listagem/refresh em execucoes;
  - abertura de logs;
  - ausencia de erro de console.
- Revise manualmente o template gerado em `Dashboard/dashboard.html` quando houver mudanca na experiencia final.

## Troubleshooting
- Se o validador acusar funcao ausente, compare o template com a lista de funcoes obrigatorias em `Tools/Test-DashboardTemplate.ps1`.
- Se houver regressao de responsividade, procure primeiro wrappers de tabela, media queries e tokens em `:root`.
- Se o HTML estiver recebendo logica demais, mova o calculo para Python, PowerShell ou para a etapa que monta o JSON de entrada.
- Se a interface depender de assets novos, valide primeiro se `lib/assets/` ja contem uma alternativa suficiente.

## Pre-Delivery Checklist
- Confirme que o HTML continua separado da logica de negocio.
- Confirme que os assets reutilizados sao os compartilhados do repositorio quando possivel.
- Confirme que o template continua passando no check de dashboard.
- Confirme que a mudanca preserva legibilidade em desktop e mobile.
