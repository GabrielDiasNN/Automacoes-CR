# Automacao - Receitas Emitidas (Nativo v2.5.0 - Pure-Python) 🌟

## Visao Geral

Este projeto automatiza a geracao e distribuicao do relatorio semanal de **Receitas Emitidas** para a Cozinha de Quimicos. Esta automacao e o estandarte da arquitetura **Nativa (VBA-Free)**, operando de forma 100% independente do Excel e PowerQuery, com foco em performance e integridade tecnica.

## Fluxo do Processo (Arquitetura IPC Stdio Blindada)

A execucao ocorre inteiramente em memoria, utilizando comunicacao inter-processo de alta performance:

`Oracle DB` -> `extract_oracle.py` (JSON via Stdout) -> `generate_html_report.py` (HTML via Stdout) -> `run.ps1` -> `Outlook COM`

---

## Componentes do Projeto

### 1. Orquestrador PowerShell (`run.ps1`)
Gerencia o fluxo "Padrao Ouro":
- Realiza o **Pre-Flight Check** completo antes da execucao.
- Coordena a passagem de dados via *Stdio Pipes*, implementando a limpeza de BOM (`utf-8-sig`) para garantir compatibilidade entre PowerShell 5.1 e Python.
- Dispara o e-mail via Outlook COM (Outlook-Safe), mantendo a aplicacao viva para garantir o envio total da *Outbox*.

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
- **Base64 Bridge Protocol**: Todas as mensagens de log (Python -> PowerShell) sao transportadas via Base64 para garantir integridade total do Portugues (PT-BR).
- **ASCII-Safe Source**: O codigo-fonte das mensagens utiliza apenas caracteres ASCII e sequencias de escape, tornando-o imune a erros de encoding de editores.
- **Auto-Masking**: Protecao automatica de PII e segredos nos arquivos de log.

### Codigos de Saida (Exit Codes)
- `0`: Sucesso Absoluto.
- `1`: Falha tecnica tratada.
- `9`: Falha de Ambiente (Pre-Flight).

---

## Legado
Os artefatos originais baseados em Excel/VBA foram movidos para a pasta **`Legacy/`**. Esta automacao provou a viabilidade tecnica da migracao para 100% Python no ecossistema Costa Rica Malhas.
