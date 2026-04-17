# Automação - Receitas Emitidas

## Visão Geral

Este projeto automatiza a geração e distribuição do relatório semanal de **Receitas Emitidas** para a Cozinha de Químicos. O foco é fornecer uma visão compacta e organizada por máquinas para a conferência física operacional.

## Fluxo do Processo

`MonitorAutomacoes.ps1` (Orquestrador) -> `run.ps1` (Runner PS) -> `Excel COM` (VBA) -> `Power Query` -> `Email Outlook`

---

## Componentes do Projeto

### 1. Runner PowerShell (`run.ps1`)
Runner nativo que utiliza a `lib/Lib-Logging.psm1` para garantir a conformidade dos logs:
- Inicia a instância do Excel em modo invisível via COM.
- Realiza a verificação de compilação preventiva no projeto VBA.
- Executa a macro principal `ProcessarRelatorioSemanal`.
- Monitora o log consolidado para detecção de sucesso ou falha.

### 2. Workbook Excel (`Controle de Receitas Emitidas.xlsm`)
Contém a inteligência de processamento:
- **Agrupamento por Máquina**: Utiliza Tabelas Dinâmicas para consolidar os dados extraídos via Power Query.
- **Configuração de Destinatários**: Aba `Config` com tabela de endereços (`Para`/`CC`).
- **Conversão HTML**: Transforma a planilha em um corpo de e-mail otimizado para Outlook.

---

## Operação e Manutenção

### Logs e Diagnóstico
- **Log Unificado**: `Logs/ReceitasEmitidas.log`.
  - Contém a trilha consolidada: `[PS]` (PowerShell) e `[VBA]` (Excel).

### Códigos de Saída (Exit Codes)
- `0`: Sucesso.
- `6`: VBA reportou falha ou erro fatal (conferir log detalhado).
- `7`: Workbook bloqueado (somente leitura).
- `8`: Falha de compilação VBA detectada antes da execução.

### Regras de Negócio Críticas
1. **Frequência Semanal**: Configurado no `config.json` para disparar toda sexta-feira às 07:05 AM.
2. **Atualização de Dados**: O relatório é alimentado por consultas Power Query integradas que requerem conexão estável para extração das ordens emitidas na semana.
