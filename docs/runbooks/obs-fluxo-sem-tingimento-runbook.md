# Runbook — OBs Fluxo Sem Tingimento (OFST-06)

Automação que avisa o grupo **Expedição Tinturaria** quando uma OB de fluxo 204 (sem tingimento) tem peça suficiente no depósito 95 para ser montada, com pedido comercial não terminado em R/S. Detalhes de arquitetura: [OBs Fluxo Sem Tingimento/README.md](../../OBs%20Fluxo%20Sem%20Tingimento/README.md) · decisões: [CONTEXT.md](../../OBs%20Fluxo%20Sem%20Tingimento/CONTEXT.md).

> **Status: ativada em produção desde 16/07/2026, 17:00.** Registrada no Orchestrator (`id=5`, `catalog_id=OFST-06`). Ver "Ativação" no fim deste runbook para a evidência da primeira execução real.

## Diagnóstico rápido

```powershell
# Últimos logs
Get-Content "OBs Fluxo Sem Tingimento\Logs\Ofst.jsonl" -Tail 40

# O que a automação decidiu na última execução (resumo + falhas)
Get-Content "OBs Fluxo Sem Tingimento\ofst_result.json" -Raw | ConvertFrom-Json | Select-Object -ExpandProperty resumo

# Quais OBs já foram avisadas (idempotência)
Get-Content "OBs Fluxo Sem Tingimento\ofst_state.json" -Raw

# Reproduzir a decisão contra o Oracle SEM enviar WhatsApp
.venv\Scripts\python.exe "OBs Fluxo Sem Tingimento\test_ofst_simulation.py"
```

A simulação é a ferramenta de diagnóstico principal: ela é somente leitura e usa as mesmas validações da produção (inclusive a priorização e a alocação de estoque descritas abaixo).

## Formato da mensagem

Desde 13/11/2026 o aviso vai como **card(s) visual(is) em PNG paginado(s)** (`MAX_OBS_PER_PAGE = 15`, sem truncar OBs: `card.png` + `message.txt` em 1 página via `AUTO`, ou `card_01.png`..`card_NN.png` + `cards_manifest.json` via `-Mode BATCH` quando acima de 15 OBs ou do teto de legenda), mantendo todos os números de OB pesquisáveis no WhatsApp:

```text
🎯 *Depósito 95 - OBs Fluxo Sem Tingimento*
_2 OBs prontas para montagem_

• *OB 179605* (Art. 489 · Red. 152) — 50 pçs → pronta p/ montagem
• *OB 181323* (Art. — · Red. 12345) — 40 pçs → pronta p/ montagem
```

- O card PNG exibe por OB (`Pillow` com fontes TrueType `Arial`/`DejaVuSans` e fallback proporcional): `OB`, `Art.`, `Red.`, `Fluxo 204 (s/ tingimento)`, ação à direita (`N pçs → pronta p/ montagem`) e sublinha com **Filial destino** (`PESSOASFJ.NOMEFANTASIA`) e **Data de entrega** (`ITENSPEDIDOCOMERCIAL.EXPEDIREM`). OB sem pedido comercial associado mostra `—` nos dois campos.
- `Estoque disponível` bruto e `Tempo de consulta` ficam fora do aviso visual (seguem em `ofst_result.json` e nos logs `Logs/Ofst.jsonl`).

## Priorização e alocação de estoque

A ordem das OBs na mensagem e a decisão de quem entra seguem duas regras (`validators.priorizar_obs` + `validators.alocar_estoque`, ambas puras e testadas em `Orchestrator/tests/test_ofst.py`):

1. **Priorização**: OBs de lojas (`PEDIDOCOMERCIAL.IDFILIALRESPONSAVEL <> 1`) vêm primeiro, ordenadas por data de entrega ascendente — é onde a malha é de fato vendida. OBs da matriz (`IDFILIALRESPONSAVEL = 1`, CR-MATRIZ/PR, o depósito de malhas) vão para o **fim da lista**, também por data de entrega entre si. OB sem data de entrega vai por último dentro do próprio grupo; OB sem pedido comercial conta como loja.
2. **Alocação sequencial**: o estoque do depósito 95 é por produto (código reduzido) e as OBs concorrem por ele. Percorrendo as OBs na ordem de prioridade, cada OB só entra na mensagem se o **saldo restante** cobrir a quantidade necessária dela — e, ao entrar, a quantidade é deduzida do saldo. OBs que não couberem no estoque ficam fora da mensagem (aparecem nos logs como "estoque insuficiente ... saldo restante"). Assim a mensagem nunca lista mais OBs do que o estoque físico permite montar.

Consequência prática: uma OB da matriz só é avisada se sobrar estoque depois de atender todas as lojas do mesmo produto. Se o grupo perguntar "por que a OB X não veio na mensagem", rode a simulação — o relatório mostra o saldo no momento da avaliação de cada OB.

## Falhas comuns

### ExitCode=2 — "Nada a notificar"

**Não é falha.** Significa: nenhuma OB de fluxo 204 pendente, ou nenhuma com estoque suficiente, ou todas as elegíveis já foram avisadas. Confirme com a simulação — o relatório diz qual dos três.

### ExitCode=21 — Sessão WhatsApp expirada

Reparear a sessão `hub-global` (mesma sessão das outras automações — reparear resolve para todas):

```powershell
node lib\WhatsApp-Core.js manual VISUAL hub-global
```

### ExitCode=3 — Oracle indisponível

O extrator já tenta 3 vezes com backoff (30s/60s/120s) e tem circuit breaker. Se persistir, o problema é do banco, não da automação. Nenhum dado é perdido: nada é commitado e a próxima execução (≤120 min) reavalia tudo.

### ExitCode=4 — Falha no envio WhatsApp

Em falha total (envio único ou `0` páginas entregues em lote `BATCH`), o state **não** é commitado — todas as OBs entram de novo na próxima execução. Em falha **parcial** de lote paginado (`Lib-WhatsAppBatch.psm1`), apenas as páginas efetivamente confirmadas em `batch_result.json` permanecem em `ofst_state.json`, enquanto as OBs das páginas com falha voltam para reavaliação no próximo ciclo sem duplicar páginas já enviadas. O cleanup de Chrome zumbi do motor WhatsApp é gerenciado pelo próprio `lib/Send-WhatsApp.ps1`; se precisar inspecionar manualmente:

```powershell
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -like "*wwebjs_auth*" }
```

### Aviso "fan-out de join" nos logs

**Investigar antes de confiar no número.** Significa que os joins com `ITENS_ESTOQUE` / `TIPO_FINALIDADE_FIO` estão duplicando linhas. A automação já usa `COUNT(DISTINCT)` e está correta, mas o aviso indica que a modelagem tem cardinalidade > 1:1 — vale confirmar com o Gabriel se o filtro está pegando o que se espera. Ver D2 no [CONTEXT.md](../../OBs%20Fluxo%20Sem%20Tingimento/CONTEXT.md).

O join até o pedido comercial (filtro R/S) tem seu próprio risco de fan-out, já mapeado e mitigado — ver D7 no mesmo CONTEXT.md.

### OB foi avisada de novo sem motivo

Esperado em um caso: a OB foi montada (saiu da query, saiu do state) e depois voltou a ficar pendente. Fora isso, inspecione `ofst_state.json`.

### Forçar reenvio de todas as OBs elegíveis

```powershell
Remove-Item "OBs Fluxo Sem Tingimento\ofst_state.json"
pwsh -File "OBs Fluxo Sem Tingimento\run.ps1"
```

Apaga a memória de quem já foi avisado — o próximo envio inclui **todas** as OBs com estoque. Use só quando o grupo perdeu as mensagens.

## Execução manual

```powershell
# Completa (ENVIA WhatsApp de verdade)
pwsh -File "OBs Fluxo Sem Tingimento\run.ps1"

# Só extração e validação, sem envio
.venv\Scripts\python.exe "OBs Fluxo Sem Tingimento\extract_ofst.py" manual
```

## Ativação (checklist) — concluída em 16/07/2026

1. [x] Descobrir o ID do grupo: `node lib\WhatsApp-Core.js manual LIST_GROUPS hub-global` (quando `getChats()`/`Collections` falhar em sessões antigas, o motor faz fallback para captura por eventos por `LIST_GROUPS_CAPTURE_MS`) — `<id-do-grupo>@g.us` do grupo *Expedição Tinturaria* (16/07/2026)
2. [x] Gravar `OFST_WHATSAPP_TARGET=<id>@g.us` no `.env` (gravado na máquina local; repetir em outras máquinas — `.env` não é versionado)
3. [x] Rodar `test_ofst_simulation.py` e validar o relatório com o Gabriel — dados confirmados OK em 16/07/2026, sem fan-out (query de OBs e query de artigo/pedido comercial)
4. [x] Confirmar a janela do cron com a operação da Expedição Tinturaria — `05:00–20:00`, Seg–Sáb (`0 5-20 * * 0-5`; convenção do runtime é `0=Segunda`, não Vixie)
5. [x] Execução manual do `run.ps1` (16/07/2026, 16:55) — `ExitCode=2`, pipeline completo sem erros (nenhuma OB com estoque suficiente no momento, então nenhuma mensagem foi enviada — comportamento correto, não é falha)
6. [x] Registrada no Orchestrator via `POST /api/automations/preflight` + `create` (`id=5`, `catalog_id=OFST-06`, `enabled=true`)
7. [x] Primeira execução real via cron do Orchestrator (16/07/2026, 17:00:15) — `CRON_5_1784232000`, `status=SUCCESS`, `exit_code=2`, `requested_by=CRON`, duração 9,1s. Confirma o pipeline de ponta a ponta (pré-flight → Oracle → validação → idempotência) rodando de forma 100% automática, sem intervenção manual.

**Nenhum WhatsApp foi enviado ainda** porque, no momento da ativação, a única OB de fluxo 204 pendente (OB #179605) não tinha estoque suficiente (precisava de 50 peças, depósito 95 tinha 30). Isso é esperado — o primeiro envio real acontecerá automaticamente assim que uma OB elegível tiver estoque suficiente, sem necessidade de nova ativação.

> **Cron atualizado em 17/07/2026** (item 4 acima reflete a janela original da ativação): agendamento vigente é `["0 5-19/2 * * 0-4", "0 5-13/2 * * 5"]` — a cada 120 min, 05:00–19:00 Seg–Sex e 05:00–13:00 Sáb. Ver decisão D9 em `OBs Fluxo Sem Tingimento/CONTEXT.md`.
