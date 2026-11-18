# Automacao - Receitas Emitidas (Nativo v2.6.0 - Pure-Python) 🚀

[⬅️ Voltar para o Hub Central](../README.md)

## Visao Geral

Este projeto automatiza a geracao e distribuicao do relatorio semanal de **Receitas Emitidas** para a Cozinha de Quimicos. Esta automacao e o estandarte da arquitetura **Nativa (VBA-Free)**, operando de forma 100% independente do Excel e PowerQuery, com foco em performance e integridade tecnica.

## Fluxo do Processo (Arquitetura IPC Stdio Blindada)

A execucao ocorre inteiramente em memoria, utilizando comunicacao inter-processo de alta performance:

`Oracle DB` -> `extract_oracle.py` (JSON via Stdout) -> `generate_html_report.py` (HTML via Stdout) -> `run_receitas.py` (orquestra, sobre `lib/python/hub_runner.py`) -> `lib/Invoke-OutlookEmail.ps1` -> `Outlook COM`

---

## Componentes do Projeto

### 1. Orquestrador Python (`run_receitas.py`)
Gerencia o fluxo "Padrao Ouro", sobre o runner compartilhado `lib/python/hub_runner.py`:
- Realiza o **Pre-Flight Check** completo antes da execucao: Oracle Client (fora do modo `queue`), disco, caminhos e o check Oracle. No modo `queue`, o worker da fila e decidido como no PowerShell.
- Mantem o **lock global RE-03** durante extracao, geracao, envio e commit do estado.
- Coordena a passagem de dados pelo *stdout* dos filhos Python: o JSON e o HTML sao lidos como dado, com limpeza de BOM (`utf-8-sig`).
- Dispara o e-mail pela CLI `lib/Invoke-OutlookEmail.ps1` (Outlook COM), com 2 tentativas.
- Fecha toda execucao com o evento de fim e a telemetria. Excecao nao prevista vira `ERRO FATAL` com exit 1.

`run.ps1` agora e um **shim**: resolve o interpretador do projeto, chama `run_receitas.py`, repassa o `ExecId` e o `-DryRun` e sai com o mesmo exit code, porque o worker do Orchestrator le o exit code de `powershell.exe -File run.ps1`.

### 2. Extrator de Dados (`extract_oracle.py`)
Soberania em dados:
- Utiliza **Queries CTE (Common Table Expressions)** altamente otimizadas para evitar timeouts (`ORA-00028`).
- Implementa o **SQL Correlation DNA** para rastreabilidade total por DBAs.
- Entrega JSON estruturado com tratamento rigoroso de datas ISO.

### 3. Gerador de Relatorio (`generate_html_report.py`)
Inteligencia visual:
- **Layout Adaptativo**: Ajusta automaticamente o numero de colunas (2 ou 3) e o tamanho da tipografia baseado no "Volume Score" dos dados.
- **Entidades HTML**: Converte caracteres PT-BR para entidades (ex: `&aacute;`), garantindo que o relatorio seja inquebravel em qualquer cliente de e-mail (Desktop/Mobile).

---

## Engenharia e Seguranca

### Logs e Integridade
- **Envelope estruturado**: os eventos seguem `docs/log-event.schema.json` e vao para `Logs/ReceitasEmitidas.jsonl`. Eventos com mais de 15 dias saem do arquivo no inicio de cada execucao.
- **Saida em UTF-8**: os filhos Python recebem `PYTHONUTF8=1` e `PYTHONIOENCODING=utf-8`. O stdout e dado (JSON e HTML); o stderr vira evento de log.
- **Auto-Masking**: Protecao automatica de PII e segredos nos arquivos de log.

### Protocolo V.A.L.E.G. - Idempotência e Controle de Estado
A automação possui controle rigoroso de estado para evitar execuções redundantes e e-mails duplicados:
- **`receitas_state.json`**: Arquivo de estado persistente que armazena o Hash (SHA-256) do último payload extraído.
- Se o `extract_oracle.py` identificar que os dados recém extraídos possuem o mesmo Hash da execução anterior, ele encerra antecipadamente emitindo o **ExitCode 2**.
- O Orquestrador intercepta esse código como sucesso sem alterações e interrompe a cadeia de processamento visual (evitando o acionamento do gerador HTML e do e-mail).

---

### Codigos de Saida (Exit Codes)
- `0`: Sucesso. Inclui a idempotencia: extracao sem alteracoes (ExitCode 2 do extrator) encerra com 0, sem e-mail.
- `1`: Erro fatal (`ERRO FATAL`): envio sem sucesso, transformacao vazia ou excecao nao prevista.
- `3`: Falha definitiva na extracao Oracle.
- `9`: Falha de Ambiente (Pre-Flight).
- `26`: Worker Oracle da fila offline. O Orchestrator reenfileira quando o heartbeat voltar.
- `27`: Prazo da fila Oracle esgotado com o worker vivo.

---

## Execucao manual (validacao)

Uso de validacao, nao de producao. O `--dry-run` roda pre-flight, extract e transform de verdade, mas nao envia e-mail e nao confirma o estado: a execucao so registra o que faria. Ele tambem pega o lock RE-03, entao nao rode junto com a execucao agendada.

Informe um `ExecId` manual, sem o prefixo `TEL_`. Sem `ExecId`, o runner registra a telemetria no Orchestrator (quando ha `ORCHESTRATOR_API_KEY` no `.env`). Com `ExecId` manual, a execucao fica sem telemetria: nenhuma chamada ao Orchestrator na abertura nem no fechamento. O log continua em `Logs/ReceitasEmitidas.jsonl`.

```powershell
.venv\Scripts\python.exe "Receitas Emitidas\run_receitas.py" VALIDACAO_MANUAL_0001 --dry-run
```

Pelo shim, com o mesmo efeito:

```powershell
powershell.exe -NoProfile -File "Receitas Emitidas\run.ps1" -ExecId VALIDACAO_MANUAL_0001 -DryRun
```

Em worktree, use o `.venv` da raiz do repositorio principal (o shim resolve sozinho).

---

## 🧠 Gestão de Contexto (AI-Native)
Este arquivo é o mapa cognitivo local do robô de Receitas Emitidas.
- **Obrigação**: Deve ser atualizado após mudanças na query SQL (Oracle), na lógica de geração do relatório adaptativo, sempre que a versão (v2.x.x) for incrementada ou o protocolo de saída for alterado.
- **Sincronismo**: Garante que a IA compreenda o fluxo de memória via Stdout Pipes (IPC) e o controle de estado SHA-256.
- **Objetivo**: Manter a IA informada sobre o estado de excelência e independência de Excel deste módulo.
