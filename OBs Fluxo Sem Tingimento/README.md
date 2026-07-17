# OBs Fluxo Sem Tingimento (OFST-06)

[⬅️ Voltar para o Hub Central](../README.md)

Consulta as OBs de **fluxo 204** (direto para rama, sem tingimento) que já foram emitidas mas ainda não montadas, exclui pedidos comerciais terminados em **R** ou **S**, confronta a necessidade de peças com o estoque disponível no **depósito 95** e avisa o grupo **Expedição Tinturaria** no WhatsApp quando há peça suficiente para montar.

| Item | Valor |
|---|---|
| ID | `OFST-06` |
| Entrypoint | `run.ps1` |
| Agendamento | A cada 120 min, 05:00–19:00 Seg–Sex, e 05:00–13:00 Sáb (campo `schedule` do manifesto) |
| Canal | WhatsApp — grupo Expedição Tinturaria |
| Dependências | Oracle (somente leitura), motor WhatsApp `lib/` |

---

## 🚦 Antes de ativar: rodar as simulações (FASE 1)

**A simulação é obrigatória antes de ligar o job.** Ela roda as queries reais contra o Oracle e passa os retornos pelas **mesmas funções de `validators.py` que a produção usa** — o que você aprova aqui é literalmente o que vai rodar depois.

A simulação é **somente leitura**: não escreve state, não gera `message.txt` e **não envia WhatsApp**. Pode rodar quantas vezes quiser.

```powershell
# 1. Simulação completa (usa a 1a OB retornada como peça de amostra)
.venv\Scripts\python.exe "OBs Fluxo Sem Tingimento\test_ofst_simulation.py"

# 2. Simulação apontando uma peça conhecida na Validação 2
.venv\Scripts\python.exe "OBs Fluxo Sem Tingimento\test_ofst_simulation.py" --codigo 12345
```

Saída esperada:

```
======================================================================
SIMULAÇÃO OBs FLUXO SEM TINGIMENTO (OFST-06) — somente leitura
======================================================================

=== Validação 1: Query de OBs (FLUXO=204, STATUS=1, OBMONTADA='0') ===
✓ Validação OB Query: 8 OBs encontradas (STATUS=1, FLUXO=204)
    amostra -> OB #1001 | peça 12345 | 50 un | 120.5 kg

=== Validação 2: Query de Estoque (Peça 12345) ===
✓ Validação Estoque Query (Peça 12345): 75 unidades disponíveis

=== Validação 3: Comparação Lógica (estoque >= necessidade) ===
✓ OB #1001 precisa 50 un, tem 75 un → Notificar ✅
✗ OB #1002 precisa 100 un, tem 12 un → Sem estoque ❌
----------------------------------------------------------------------
Relatório Final: ✓ 8 OBs válidas, ✗ 0 OBs com erro | 3 a notificar, 5 sem estoque | tempo total: 1.2s
----------------------------------------------------------------------

Nenhum WhatsApp foi enviado — esta é uma simulação de leitura.
```

Exit code `0` = todas as validações passaram. `1` = alguma reprovou (o relatório diz qual).

### O que conferir no relatório

1. **A contagem de OBs faz sentido?** Se vier 0, ou um número muito diferente do esperado, a query ou os domínios (`STATUS=1`, `OBMONTADA='0'`) precisam de revisão.
2. **A amostra bate com o SGT?** Confira 1–2 OBs na tela do sistema: peça, total de peças e kg.
3. **Apareceu aviso de fan-out?** Ver "Risco de fan-out" abaixo — é o ponto mais importante da revisão.
4. **As comparações fazem sentido?** OB que o PCP sabe estar pronta deveria aparecer com ✅.

---

## ⚠️ Risco de fan-out de join (por que há duas contagens)

A query de estoque usa **`COUNT(DISTINCT IDPECASPRODUTO)`** como valor autoritativo, e não o `COUNT()` simples.

`ITENS_ESTOQUE` e `TIPO_FINALIDADE_FIO` entram na query **apenas como filtro** — nenhuma coluna delas é projetada. Se qualquer uma tiver mais de uma linha por chave de junção, o `COUNT()` simples **conta a mesma peça várias vezes**, superestima o estoque e a OB seria notificada como "pronta" sem peça real no depósito.

Por isso a query devolve as duas contagens:

| Coluna | Papel |
|---|---|
| `QTD_PECAS_DISPONIVEIS` | `COUNT(DISTINCT ...)` — **valor usado na decisão** |
| `QTD_LINHAS_BRUTAS` | `COUNT(...)` — linhas após os joins |

Se as duas divergirem, `validators.validate_estoque_row` marca `tem_fan_out` e a simulação avisa em vermelho. **Se isso aparecer, vale revisar os joins com o Gabriel antes de ativar** — significa que a modelagem tem cardinalidade maior que 1:1 e a query original do spec estaria errada.

## ⚠️ Fan-out no join do pedido comercial (filtro R/S)

O caminho até `PEDIDOCOMERCIAL.PEDIDOCLIENTE` (usado para excluir pedidos terminados em R/S) passa por `PEDPRODUCAOOB → OFORDENS → OFPEDIDO → ITENSPEDIDOQTDES → ITENSPEDIDOGRADE → ITENSPEDIDOCOMERCIAL → PEDIDOCOMERCIAL`. Amostragem real (16/07/2026, 1293 OBs históricas de fluxo 204) confirmou fan-out em ~1,4% dos casos, causado por um pedido "placeholder" (`PEDIDOCLIENTE='0'`) que convive com o pedido comercial real. O filtro `OFP.QUANTIDADE_ATUAL <> 0` (mesmo usado em `OBs Paradas Fase`) elimina esse placeholder — validado sem nenhum caso residual de fan-out ou `PEDIDOCLIENTE` conflitante na mesma amostra. Ver detalhes no cabeçalho de [SQL-ObsFluxoSemTingimento.sql](SQL-ObsFluxoSemTingimento.sql) e na decisão D7 do [CONTEXT.md](CONTEXT.md).

---

## 🔌 Configurar o destino WhatsApp

O ID do grupo **nunca** fica versionado. Ele vive em `OFST_WHATSAPP_TARGET` no `.env` local.

Já encontrado nesta máquina em 16/07/2026: grupo **"Expedição Tinturaria"** = `554796989039-1616873564@g.us` (gravado no `.env` local). **Em qualquer outra máquina, `.env` não é versionado — repita a descoberta:**

```powershell
# 1. Descobrir o ID do grupo com o motor interno
node lib\WhatsApp-Core.js manual LIST_GROUPS hub-global
```

> O comando falhava até a v2.8.0 da lib com `Erro ao listar grupos: r | r` (`client.getChats()` quebrava na serialização — mesma classe de bug do CHANGELOG [1.1.7] para `sendMessage`). Corrigido na v2.8.1 (`lib/WhatsApp-Core.js`, ver [1.2.0] no CHANGELOG): agora lê `window.Store.Chat` diretamente via Puppeteer.

```powershell
# 2. Copiar o id (formato <numero>-<timestamp>@g.us) para o .env
#    OFST_WHATSAPP_TARGET=...@g.us
```

O `contactId` em `whatsapp-config.json` é só placeholder de fallback.

---

## ▶️ Executar (FASE 2 — integração)

```powershell
# Execução manual completa (EXTRAI + ENVIA WhatsApp de verdade)
pwsh -File "OBs Fluxo Sem Tingimento\run.ps1"

# Só a extração + validação, sem envio (gera ofst_result.json)
.venv\Scripts\python.exe "OBs Fluxo Sem Tingimento\extract_ofst.py" manual
```

### Testes automatizados (sem Oracle)

```powershell
cd Orchestrator; ..\.venv\Scripts\pytest.exe tests\test_ofst.py -v
```

---

## 🔄 Idempotência — por OB, não por lote

O job roda de hora em hora, então **não pode reavisar a mesma OB a cada execução**.

`ofst_state.json` guarda os IDs de OB já notificados. A cada execução:

- OB notificável que **já está no state** → ignorada (não entra na mensagem);
- OB notificável **nova** → entra na mensagem;
- OB que saiu da query (foi montada) → **removida do state**. Se voltar a ficar pendente, avisa de novo.

O commit do state (`ofst_state.json.tmp` → `ofst_state.json`) acontece **somente após o envio confirmado** no `run.ps1`. Se o WhatsApp falhar, o state não é commitado e as OBs são reavaliadas na execução seguinte — a falha nunca engole um aviso.

> Um hash do lote inteiro (padrão do OBP-04) **não serviria aqui**: o estoque flutua a cada hora, o hash mudaria sozinho e a mesma OB seria reavisada.

---

## 📤 Exit codes

| Código | Significado |
|---|---|
| `0` | Sucesso — OBs novas notificadas |
| `2` | Nada a notificar (sem OB, sem estoque, ou todas já avisadas) |
| `3` | Falha definitiva na extração Oracle (após 3 tentativas) |
| `4` | Falha na montagem da mensagem ou no envio WhatsApp |
| `9` | Falha de pré-flight (Oracle/Python/config ausente) |
| `21` | WhatsApp exige reautenticação (parear a sessão de novo) |

---

## 🗂️ Estrutura

| Arquivo | Papel |
|---|---|
| `run.ps1` | Orquestrador: pré-flight → extração → mensagem → envio → commit do state |
| `extract_ofst.py` | Oracle → validação → `ofst_result.json` (produção) |
| `validators.py` | **Regras de confiabilidade — funções puras, sem I/O** |
| `queries.py` | Carrega os `.sql` e monta a query de estoque com bind variables |
| `models.py` | Dataclasses do domínio (OB, Estoque, Avaliação, Resumo) |
| `errors.py` | Exceções: falha de contrato vs. falha de dado |
| `format_message.py` | `ofst_result.json` → `message.txt` |
| `test_ofst_simulation.py` | Simulação FASE 1 contra Oracle real (somente leitura) |
| `SQL-ObsFluxoSemTingimento.sql` | Query das OBs candidatas (fluxo, montagem, artigo cru, filtro R/S) |
| `SQL-EstoqueDeposito95.sql` | Query de estoque parametrizada por bind |
| `whatsapp-config.json` | Destino e sessão do canal (ID real vem do `.env`) |

Documentação de decisões e estado: [CONTEXT.md](CONTEXT.md) · Runbook: [docs/runbooks/obs-fluxo-sem-tingimento-runbook.md](../docs/runbooks/obs-fluxo-sem-tingimento-runbook.md)
