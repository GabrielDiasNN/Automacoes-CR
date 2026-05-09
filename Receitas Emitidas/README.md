# Automacao - Receitas Emitidas (Nativo v2.6.0 - Pure-Python) 🚀

[⬅️ Voltar para o Hub Central](file:///c:/Automacoes/README.md)

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

### Protocolo V.A.L.E.G. - Idempotência e Controle de Estado
A automação possui controle rigoroso de estado para evitar execuções redundantes e e-mails duplicados:
- **`receitas_state.json`**: Arquivo de estado persistente que armazena o Hash (SHA-256) do último payload extraído.
- Se o `extract_oracle.py` identificar que os dados recém extraídos possuem o mesmo Hash da execução anterior, ele encerra antecipadamente emitindo o **ExitCode 2**.
- O Orquestrador intercepta esse código como sucesso sem alterações e interrompe a cadeia de processamento visual (evitando o acionamento do gerador HTML e do e-mail).

---

## 🧠 Gestão de Contexto (AI-Native)
Este arquivo é o mapa cognitivo local do robô de Receitas Emitidas.
- **Obrigação**: Deve ser atualizado após mudanças na query SQL (Oracle) ou na lógica de geração do relatório adaptativo.
- **Sincronismo**: Garante que a IA compreenda o fluxo de memória via Stdout Pipes (IPC) e o controle de estado SHA-256.

### Codigos de Saida (Exit Codes)
- `0`: Sucesso Absoluto.
- `1`: Falha tecnica tratada.
- `2`: Sucesso / Idempotência (Sem alterações nos dados, fluxo interrompido).
- `9`: Falha de Ambiente (Pre-Flight).

---

## Legado
Os artefatos originais baseados em Excel/VBA foram movidos para a pasta **`Legacy/`**. Esta automacao provou a viabilidade tecnica da migracao para 100% Python no ecossistema Costa Rica Malhas.

---

## 🧠 Gestão de Contexto (AI-Native)
- **Obrigação:** Atualizar este README sempre que a versão (v2.x.x) for incrementada ou o protocolo de saída for alterado.
- **Objetivo:** Manter a IA informada sobre o estado de excelência e independência de Excel deste módulo.
