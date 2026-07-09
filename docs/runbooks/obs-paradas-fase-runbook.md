# Runbook — OBs Paradas Fase (OBP-04)

[⬅️ Voltar para o Hub Central](../../README.md)

## Diagnóstico rápido

```powershell
# Ver últimos logs
Get-Content "OBs Paradas Fase\Logs\*.log" -Tail 50

# Verificar sessão WhatsApp
Test-Path "lib\.wwebjs_auth\session-hub-global\Default\Local Storage\leveldb\*.log"
```

## Falhas comuns

### ExitCode=21 — Sessão expirada
```
lib\Authenticate-WhatsApp.bat
```
Escaneie o QR code. Aguarde "Cliente pronto" antes de fechar.

### ExitCode=24 — Chrome não inicializa
Verificar processos zumbi:
```powershell
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object { $_.CommandLine -like "*wwebjs_auth*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
Depois re-autenticar.

### ExitCode=3 — Oracle indisponível
Verificar conectividade Oracle (string em `ORACLE_CONNECT_STRING` no `.env`). Aguardar recovery automático (3 tentativas com backoff 30/60/120s).

### Resetar delivery_state.json (forçar reenvio de todas as fases)

Use quando o lote foi alterado externamente ou quando as fases precisam ser reenviadas independente do hash salvo:

```powershell
Remove-Item "OBs Paradas Fase\delivery_state.json" -Force -ErrorAction SilentlyContinue
Remove-Item "OBs Paradas Fase\obs_state.json"      -Force -ErrorAction SilentlyContinue
Remove-Item "OBs Paradas Fase\obs_state.json.tmp"  -Force -ErrorAction SilentlyContinue
```

Na próxima execução, o script tratará todas as fases como não entregues e realizará um novo envio completo.

### ExitCode=4 — Falha parcial de fases (algumas entregues, outras não)

Verificar quais fases falharam:
```powershell
Get-Content "OBs Paradas Fase\delivery_state.json" | ConvertFrom-Json | Select-Object -ExpandProperty phases
```

As fases com `success=false` serão reenviadas automaticamente na próxima execução agendada (sem intervenção). Para forçar reenvio imediato:
```powershell
# Opção 1: aguardar próximo cron (05:30, 14:00 e 22:30 [Seg-Sáb] ou 23:00 [Dom])
# Opção 2: acionar manualmente via Orchestrator API
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/automations/OBP-04/trigger" -Method POST -Headers @{"X-API-Key"="<api_key>"}
```

Para forçar reenvio de TODAS as fases (ignorar estado):
```powershell
Remove-Item "OBs Paradas Fase\delivery_state.json" -Force -ErrorAction SilentlyContinue
Remove-Item "OBs Paradas Fase\obs_state.json"      -Force -ErrorAction SilentlyContinue
```

### Mensagens na fila (ACK não confirmado)
Abrir Chrome virtual com sessão hub-global para drenar a fila:
```powershell
pwsh -File lib\Keep-WhatsApp-Open.ps1
```

### Configuração de responsável/threshold por fase (100% por código, desde v9.5.20)

`config.json` mapeia fase → responsável/threshold exclusivamente pelo **código numérico
da fase** (`CODIGO_FASE`, exposto em `obs_result.json` via `SQL-ObsParadasFase.sql`).
Não existe mais matching por palavra-chave/substring — cada fase monitorada precisa de
uma entrada explícita em `fases_monitoradas`, chaveada pelo código exato:

```json
"fases_monitoradas": {
  "26": {
    "descricao": "IVF-INVERSÃO P/FELPAGEM",
    "ativo": true,
    "threshold_dias": 1,
    "responsavel": "lider_3_turno"
  }
}
```

O campo `descricao` é só para **manutenção visual** (mostra qual fase Oracle aquele
código representa) — não é lido pelo código, então pode ficar desatualizado sem quebrar
nada, mas mantenha-o correto por clareza.

**`responsavel` referencia uma variável de `contatos` (nunca um número de telefone
direto)** — ver seção seguinte. Isso centraliza a manutenção: trocar o número de um
líder de turno em um único lugar (`contatos`) já propaga para todas as fases que usam
aquela variável.

O campo **`ativo`** (booleano, default `true` se omitido) liga/desliga o monitoramento
daquela fase sem precisar remover a entrada do arquivo. Com `"ativo": false`, a fase
continua documentada em `config.json` (descrição, threshold e responsável preservados
para referência futura), mas nenhuma OB parada nela gera card ou entra na mensagem do
WhatsApp — útil para fases que foram mapeadas por código (para não colidir com outras
no matching), mas que não precisam de alerta ativo agora. Basta trocar para `true` quando
quiser reativar, sem precisar redigitar o resto da configuração.

Para descobrir o código de uma fase, consulte `SGTPRD.FASES_FLUXO` no Oracle
(`CODIGO_FASE` / `DESCRICAO_FASE`) ou inspecione `CODIGO_FASE` nas linhas de
`obs_result.json` após a próxima extração. **Fases sem entrada em `fases_monitoradas`
simplesmente não são monitoradas** — não existe mais fallback por palavra-chave, então
uma fase nova precisa ser adicionada explicitamente aqui para começar a gerar alertas.

Demais seções do `config.json`:
- `filtros_por_codigo_fase`: filtro adicional por campo do OB (chave = código de fase,
  valor = `{campo: valor_esperado}`), ex.: `"20": {"CODIGO_FLUXO": 204}` restringe a fase
  20 a OBs desse fluxo específico.
- `ordem_codigos_fase`: objeto `{codigo: descricao}` (não é lista) controlando a ordem de
  exibição dos cards/seções na mensagem do WhatsApp (não afeta responsável/threshold, é só
  cosmético). A descrição fica ao lado do código propositalmente, para reorganizar a ordem
  olhando o nome da fase em vez de precisar cruzar com `fases_monitoradas`:
  ```json
  "ordem_codigos_fase": {
    "20": "RMC-REVISÃO MALHA CRUA",
    "46": "PPA-PREPARAÇÃO AMACIANTE"
  }
  ```

### Contatos (variáveis de responsável, desde v9.5.20; migrado para `.env` na v9.5.34)

Os números reais de responsável nunca ficam versionados em `config.json` — vivem só no
`.env` local (nunca commitado), em variáveis `OBP_CONTATO_<PAPEL>` (ver `.env.example`).
`fases_monitoradas.responsavel` referencia apenas o **nome do papel** (ex.: `lider_1_turno`),
nunca um número literal; `generate_phase_cards.py`/`format_message.py` resolvem cada papel
lendo a variável de ambiente correspondente em tempo de execução.

```
# .env (não versionado)
OBP_CONTATO_LIDER_1_TURNO=<numero>
OBP_CONTATO_EQUIPE_CQ=<numero1>,<numero2>,<numero3>
```

**Para trocar o número de um líder, edite só o `.env`** — todas as fases cuja
`responsavel` referencia esse papel recebem o número novo automaticamente, sem precisar
editar `fases_monitoradas`. `equipe_cq` aceita múltiplos números separados por vírgula
(todos recebem menção na mesma mensagem).

Papéis hoje configurados: `lider_1_turno` / `lider_reserva_1_turno`, `lider_2_turno` /
`lider_reserva_2_turno`, `lider_3_turno` / `lider_reserva_3_turno` e `equipe_cq` (3
contatos). Os nomes/números reais de cada papel estão só no `.env` de produção.

#### Fases monitoradas hoje (levantado em 03/07/2026 via consulta em `SGTPRD.FASES_FLUXO`)

| Código | Fase (Oracle) | Responsável (papel — número real no `.env`) | Ativo |
|---|---|---|---|
| 20 | RMC-REVISÃO MALHA CRUA | `lider_3_turno` | sim |
| 25 | CDP-CONFERENCIA DE PESO | `equipe_cq` | **não** |
| 26 | IVF-INVERSÃO P/FELPAGEM | `lider_3_turno` | sim |
| 45 | CDC-CONFERENCIA DE COR | `lider_reserva_3_turno` | sim |
| 46 | PPA-PREPARAÇÃO AMACIANTE | `lider_1_turno` | sim |
| 47 | UMM-UMEDECIMENTO DE MALHA | `lider_reserva_3_turno` | sim |
| 50 | HID-HIDRO UMIDO | `lider_1_turno` | sim |
| 55 | HIS-HIDRO SECO | `lider_1_turno` | sim |
| 60 | SEC-SECADOR | `lider_1_turno` | sim |
| 65 | FEL-FELPAGEM | `lider_reserva_1_turno` | sim |
| 70 | CLB-CALANDRA DE BRILHO | `lider_reserva_1_turno` | sim |
| 80 | CLC-CALANDRA DE COMPACTACAO | `lider_reserva_1_turno` | sim |
| 90 | ABR-ABRIDOR | `lider_2_turno` | sim |
| 100 | RAU-RAMAR UMIDO | `lider_2_turno` | sim |
| 110 | RAS-RAMAR SECO | `lider_2_turno` | sim |
| 150 | EXP-EXPEDICAO ACABADO | `lider_reserva_2_turno` | sim |
| 160 | CDQ-CONTROLE DE QUALIDADE | `equipe_cq` | sim |
| 165 | CDF-CONFERÊNCIA DE FELPA | `equipe_cq` | sim |

Fase 25 está com `ativo: false` por decisão de negócio (não fazia parte do mapeamento de
turnos definido em 03/07/2026) — continua documentada, basta reativar (`"ativo": true`)
quando for necessário monitorá-la. Fases 160 e 165 antes da migração para código exato
não eram monitoradas de forma confiável (a keyword `CQ` não batia com o texto `"CDQ-..."`,
e nada batia com `"CDF-..."`).

## Evidência de SLA (verificação periódica)

SLA declarado no manifesto: **20 minutos** (o mais apertado das 4 automações registradas, coerente com o cron a cada 30 min). Última execução `SUCCESS` verificada em 05/07/2026 contra o banco real do Orchestrator: duração de **~2,5 min**, concluída em `05/07/2026 14:02:33` — dentro do SLA com folga confortável. Consulta usada (via `Orchestrator/automacoes.db`, somente leitura):
```sql
SELECT e.duration_seconds, e.finished_at FROM executions e
JOIN automations a ON a.id = e.automation_id
WHERE a.name = 'OBs Paradas Fase' AND e.status = 'SUCCESS'
ORDER BY e.finished_at DESC LIMIT 1;
```

## Drill de Falha (simulado, isolado de produção)

Drill executado em 05/07/2026 contra uma cópia isolada em memória do schema real (nunca contra `automacoes.db` de produção nem disparando WhatsApp real), usando a config real desta automação (`max_retries=0`): injetada uma execução `ERROR` sintética e uma execução `SUCCESS` com duração 15 min acima do SLA (35 min), e chamadas as funções reais `collect_sla_breaches`/`check_sla_breaches` e `prepare_requeue`.

**Resultado:** SLA breach detectado corretamente (finding `WARN` gerado). Auto-retry **corretamente bloqueado** (`RequeueValidationError: Limite de retry excedido para esta execução: 0/0`) — comportamento esperado, pois `max_retries=0` é decisão deliberada do operador para esta automação: falhas exigem intervenção manual, não recuperação automática. Dado o SLA apertado (20 min), vale reavaliar periodicamente se `max_retries=0` continua sendo a escolha certa para OBP-04 ou se um retry automático rápido reduziria o risco de breach por falha transitória.

Nota: OBP-04 compartilha `queue_group="oracle"` com as outras 3 automações em produção — retries concorrentes do mesmo grupo são serializados por design.
