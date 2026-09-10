---
name: nodejs-communications
description: Use when changing the shared WhatsApp engine, headless communication flows, or BAT/CMD bootstrap layers built in Node.js, without letting Node absorb orchestration or state ownership.
---

## Purpose
Manter o Node.js do hub restrito ao canal de comunicação (WhatsApp) e ao bootstrap local, com entrega só confirmada após ack real persistido, sem que o Node assuma orquestração, agendamento ou posse de estado corporativo.

## When to Use
- Ao alterar o motor soberano `lib/WhatsApp-Core.js` ou o wrapper `lib/Send-WhatsApp.ps1`, usados por todas as automações.
- Ao mexer nos auxiliares reais `lib/log-masking.js`, `lib/open-whatsapp-session.js`, `lib/whatsapp-auth-path.js` ou `lib/whatsapp-session-state.js`.
- Ao editar o bootstrap shell legado `Receitas Bloqueadas/RunWhatsApp.bat` ou qualquer `.bat`/`.cmd` que suba um processo Node.
- Ao revisar confirmação de ack, retry de canal, sessão/QR do WhatsApp ou o contrato de exit code entre shell, PowerShell e Node.
- Ao adicionar teste em `lib/tests/WhatsApp-Core.test.js` ou `Receitas Bloqueadas/tests/whatsapp-offline.test.js`.

## Do Not Use When
- Para definir quem dispara o canal, propagação de ExecId, idempotência ou posse de estado de execução: use a skill `enterprise-orchestration-contract`.
- Para política de segredo, mascaramento de log, severidade ou classificação de falha recuperável versus terminal: use a skill `automation-runtime-safety`.
- Para sintaxe, approved verbs ou modularização de módulos PowerShell que encapsulam o Node: use a skill `powershell-automation-monitor`.
- Para e-mail, dashboard ou relatório HTML de saída: use a skill `html-css-enterprise-standard`.
- Para código Python que chama o canal (FastAPI, worker): use a skill `python-enterprise-standard`.

## Related Skills
- `enterprise-orchestration-contract` define o dono da orquestração e como o ExecId e o estado de entrega chegam ao processo Node.
- `automation-runtime-safety` cobre Zero-Trust, mascaramento de segredo em log e a política de falha que o JS e o BAT devem seguir.
- `powershell-automation-monitor` cobre o contrato do runtime PowerShell (`lib/Send-WhatsApp.ps1`) que invoca o Node.
- `ai-native-development-standard` cobre a sincronização de documentação viva quando o contrato do canal muda.

## Non-Negotiable Rules
- Toda automação que envia WhatsApp reusa `lib/WhatsApp-Core.js` via `lib/Send-WhatsApp.ps1`; não instancie um cliente `whatsapp-web.js` paralelo por automação — o motor é soberano e compartilhado.
- Trate toda falha de canal explicitamente com `async/await`; nunca deixe uma rejeição sem `catch` virar processo zumbi. O `require('whatsapp-web.js')` no topo de `lib/WhatsApp-Core.js` torna a ausência da dependência um erro fatal imediato, não um warning silencioso.
- Não marque entrega como concluída antes do ack real do canal persistido no estado do domínio; sem ack persistido, o resultado é falha.
- Todo `.bat`/`.cmd`, a começar por `Receitas Bloqueadas/RunWhatsApp.bat`, propaga `errorlevel` coerente: falha no Node não pode virar sucesso no shell chamador.
- A suíte de unidade de `lib/WhatsApp-Core.js` roda com `node:test` e tem gate de cobertura de 90% de linhas, branches e funções (script `test` de `lib/package.json`); código novo no motor sem teste derruba o gate.
- Node fica restrito a canal e bootstrap: nada de agendar próxima execução, ler ou escrever `*_state.json` de decisão de fluxo, nem definir política de retry entre execuções — isso é do `run.ps1` e do Orchestrator (skill `enterprise-orchestration-contract`).
- Nenhum segredo hardcoded em `.js`, `.bat` ou JSON auxiliar; a política de segredo é da skill `automation-runtime-safety`.

## Repo-Specific Constraints
- `Tools/Test-NodeCommunications.ps1` roda `npm test` em cada diretório com `package.json`, hoje `lib/` e `Receitas Bloqueadas/` (fonte: `docs/governance-contracts.md` item 14).
- `lib/package.json` exige `whatsapp-web.js` real instalado; `node_modules` é gitignored, então após clonar rode `npm ci --prefix lib` uma vez com `PUPPETEER_SKIP_DOWNLOAD=true` para pular o Chromium (~200 MB) do Puppeteer.
- `Receitas Bloqueadas/package.json` não declara dependências (usa só módulos nativos do Node) e por isso sua suíte sempre roda, mesmo sem `npm ci`.
- Mantenha a persistência de entrega nos arquivos de estado do domínio em `Receitas Bloqueadas/`, não em estado paralelo apenas no Node.
- O rollout de código-fonte do Padrão de Logging já está completo (PR #43); a pendência é validar em produção e fechar o envelope do Orchestrator, então não reintroduza pontes de transporte antigas.
- Encoding de `.js`, `.json` e `.bat`: contrato em `AGENTS.md § Regras de Encoding`, não repetido aqui.

## Validation
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-NodeCommunications.ps1 -RootPath .` após mexer no canal ou no bootstrap.
- Rode `npm test --prefix lib` e confirme que a cobertura de `WhatsApp-Core.js` fica em 90% ou mais de linhas, branches e funções.
- Rode `npm test --prefix "Receitas Bloqueadas"` para o contrato offline (`tests/whatsapp-offline.test.js`).
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` quando alterar contrato de exit code ou estado de entrega.
- Exercite manualmente `RunWhatsApp.bat` para `lib/Send-WhatsApp.ps1` para `lib/WhatsApp-Core.js` e verifique a propagação de erro e o `errorlevel` final.

## Troubleshooting
- `npm test --prefix lib` falha em `require('whatsapp-web.js')`: rode `npm ci --prefix lib` com `PUPPETEER_SKIP_DOWNLOAD=true`; a dependência real é obrigatória e o import de topo não deve ser mockado.
- Gate de cobertura reprova após mudança no motor: adicione teste em `lib/tests/WhatsApp-Core.test.js` antes de subir, porque o corte é 90% em linhas, branches e funções.
- BAT aparenta sucesso com o Node falhando: audite `errorlevel`, `exit /b` e o repasse de stdout e stderr em `Receitas Bloqueadas/RunWhatsApp.bat`.
- Processo Node encerra sem confirmar envio: verifique o ponto em que o ack é persistido no estado do domínio antes de investigar timeout de rede.
- Canal começou a decidir ordem de execução ou retry de negócio: mova a decisão para o PowerShell ou o Orchestrator (skill `enterprise-orchestration-contract`) e devolva apenas status ao chamador.
- Falta de rastreabilidade nos logs do Node: confirme que o chamador injeta o ExecId e que o Node o devolve em stdout ou no erro, com mascaramento via `lib/log-masking.js`.

## Pre-Delivery Checklist
- Node continua restrito a canal de comunicação e bootstrap; nenhuma responsabilidade de orquestração foi absorvida.
- Entrega só é marcada como concluída após ack real persistido no estado do domínio.
- `Tools/Test-NodeCommunications.ps1` passa e a cobertura de `lib/WhatsApp-Core.js` está em 90% ou mais.
- Todo `.bat`/`.cmd` alterado retorna `errorlevel` coerente ao chamador.
- Nenhum segredo em `.js`, `.bat` ou JSON; encoding conforme `AGENTS.md § Regras de Encoding`.
