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

Cada OB aparece na mensagem WhatsApp com este bloco (desde 17/07/2026):

```
🎯 Depósito 95 - OBs Fluxo Sem Tingimento

OB: 179605
Artigo: 489
Reduzido: 152
Quantidade necessária: 50 peças
Estoque disponível: 60 peças
Data de entrega: 21/07/2026
Filial destino: CR-LOJA BLUMENAU
Status: ✅ Pronta para montagem
```

- **Data de entrega** = `ITENSPEDIDOCOMERCIAL.EXPEDIREM`; **Filial destino** = `PESSOASFJ.NOMEFANTASIA` da filial responsável do pedido (mesmos campos da CTE `ENTREGA_OB` de OBs Paradas Fase). OB sem pedido comercial associado mostra `—` nos dois campos.
- As linhas "Tempo de consulta" e "Grupo" foram removidas da mensagem — eram observabilidade interna. O tempo segue em `ofst_result.json` (`resumo.tempo_consulta_ms`) e nos logs (`Logs/Ofst.jsonl`).

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

O state **não** é commitado quando o envio falha — as OBs entram de novo na próxima execução. Não há risco de aviso perdido. Verifique Chrome zumbi:

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

1. [x] Descobrir o ID do grupo: `node lib\WhatsApp-Core.js manual LIST_GROUPS hub-global` — `554796989039-1616873564@g.us` (16/07/2026)
2. [x] Gravar `OFST_WHATSAPP_TARGET=<id>@g.us` no `.env` (gravado na máquina local; repetir em outras máquinas — `.env` não é versionado)
3. [x] Rodar `test_ofst_simulation.py` e validar o relatório com o Gabriel — dados confirmados OK em 16/07/2026, sem fan-out (query de OBs e query de artigo/pedido comercial)
4. [x] Confirmar a janela do cron com a operação da Expedição Tinturaria — `05:00–20:00`, Seg–Sáb (`0 5-20 * * 0-5`; convenção do runtime é `0=Segunda`, não Vixie)
5. [x] Execução manual do `run.ps1` (16/07/2026, 16:55) — `ExitCode=2`, pipeline completo sem erros (nenhuma OB com estoque suficiente no momento, então nenhuma mensagem foi enviada — comportamento correto, não é falha)
6. [x] Registrada no Orchestrator via `POST /api/automations/preflight` + `create` (`id=5`, `catalog_id=OFST-06`, `enabled=true`)
7. [x] Primeira execução real via cron do Orchestrator (16/07/2026, 17:00:15) — `CRON_5_1784232000`, `status=SUCCESS`, `exit_code=2`, `requested_by=CRON`, duração 9,1s. Confirma o pipeline de ponta a ponta (pré-flight → Oracle → validação → idempotência) rodando de forma 100% automática, sem intervenção manual.

**Nenhum WhatsApp foi enviado ainda** porque, no momento da ativação, a única OB de fluxo 204 pendente (OB #179605) não tinha estoque suficiente (precisava de 50 peças, depósito 95 tinha 30). Isso é esperado — o primeiro envio real acontecerá automaticamente assim que uma OB elegível tiver estoque suficiente, sem necessidade de nova ativação.

> **Cron atualizado em 17/07/2026** (item 4 acima reflete a janela original da ativação): agendamento vigente é `["0 5-19/2 * * 0-4", "0 5-13/2 * * 5"]` — a cada 120 min, 05:00–19:00 Seg–Sex e 05:00–13:00 Sáb. Ver decisão D9 em `OBs Fluxo Sem Tingimento/CONTEXT.md`.
