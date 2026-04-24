# Automação - Receitas Emitidas (Nativo v2.1.0)

## Visão Geral

Este projeto automatiza a geração e distribuição do relatório semanal de **Receitas Emitidas** para a Cozinha de Químicos. Esta automação é o piloto da arquitetura **Nativa (VBA-Free)**, operando de forma independente do Excel e PowerQuery.

## Fluxo do Processo (Arquitetura IPC Stdio)

A execução ocorre inteiramente em memória, sem criação de arquivos temporários de dados:

`Oracle DB` -> `extract_oracle.py` (JSON) -> `generate_html_report.py` (HTML) -> `run.ps1` -> `Send-OutlookEmail`

---

## Componentes do Projeto

### 1. Orquestrador PowerShell (`run.ps1`)
Gerencia o ciclo de vida da execução:
- Valida pré-requisitos de ambiente e caminhos absolutos.
- Injeta credenciais do arquivo `.env` da raiz nas variáveis de ambiente do processo.
- Orquestra os scripts Python via **Stdio Pipes**.
- Dispara o e-mail via Outlook COM, herdando automaticamente a assinatura local e fontes da sessão.

### 2. Extrator de Dados (`extract_oracle.py`)
Script Python especializado em dados:
- Utiliza a biblioteca oficial `oracledb` em modo Thick/Thin.
- Executa a query SQL otimizada com filtros de status e tipo (PESADA = 'NÃO').
- Realiza o tratamento de datas e tipos para entrega em JSON estruturado via `stdout`.

### 3. Gerador de Relatório (`generate_html_report.py`)
Inteligência de apresentação:
- Consome o JSON via `stdin`.
- Implementa lógica de **Layout Adaptativo**: ajusta tamanho de fontes e número de colunas baseado no volume de dados (2 ou 3 colunas).
- Regra de Lotes: Grupos de OBs contam como 1 receita única; OBs avulsas contam individualmente.
- Sanitização: Converte caracteres para entidades HTML garantindo fidelidade visual no Outlook.

---

## Operação e Diagnóstico

### Logs
- **Localização**: `Logs/ReceitasEmitidas.log`.
- **Níveis**:
    - `[PS]`: Mensagens do orquestrador PowerShell.
    - `[PY-EXTRACT]`: Trilha técnica da extração no Oracle (via stderr).
    - `[PY-HTML]`: Trilha de renderização do relatório (via stderr).

### Códigos de Saída (Exit Codes)
- `0`: Sucesso.
- `1`: Falha crítica de sistema ou banco de dados.
- `9`: Falha de pré-requisitos (ex: ambiente virtual ou config faltando).

---

## Legado
Os artefatos originais baseados em Excel/VBA foram movidos para a pasta **`Legacy/`** e não são mais utilizados na execução produtiva. Eles podem ser consultados para auditoria histórica da lógica original.
