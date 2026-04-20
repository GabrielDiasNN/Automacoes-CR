# Automação - Montagem de Terceirizados (Robô Fiscal v8.8.0)

## Visão Geral

Este projeto automatiza a validação fiscal determinística de ordens de montagem externa. O foco é garantir o cruzamento preciso entre Notas Fiscais (NF) e Ordens de Fabricação (OBs) de terceirizados, notificando divergências à equipe fiscal de forma proativa.

## Fluxo de Execução

`MonitorAutomacoes.ps1` (Monitor) -> `run.ps1` (Runner PS) -> `Excel COM` (VBA) -> `Oracle DB` -> `Email Outlook`

---

## Arquitetura de Componentes

### 1. Runner PowerShell (`run.ps1`)
Orquestrador de runtime que gerencia o ciclo de vida da automação:
- Inicia a instância do Excel em modo invisível.
- **Preflight VBA**: Invoca `Invoke-VbaCompilationCheck` para garantir que o projeto está íntegro antes da execução.
- **Monitoramento de Fluxo**: Captura o baseline dos logs e aguarda o token de conclusão (`FIM DO PROCESSO.`).
- **Gestão de Estados**: Traduz falhas de infraestrutura (COM, Timeout) ou lógica de negócio em exit codes padronizados.

### 2. Workbook Fiscal (`Validador_Notas_Montagem.xlsm`)
Núcleo da inteligência fiscal:
- **Refresh Deterministico**: Implementa a validação da coluna `VALIDA_ATUALIZACAO` no Oracle, assegurando que o processamento utilize apenas dados renovados.
- **Validação NF/OB**: Cruzamento complexo de saldos e quantidades entre camadas fiscais e operacionais.
- **Output de Notificação**: Geração de e-mails em HTML dinâmico com o resumo das divergências.

### 3. Utilitário de Reenvio (`ReenviarAlertaErros.ps1`)
Ferramenta operacional para reprocessamento de notificações:
- Permite o disparo de alertas de erro da última execução sem a necessidade de um novo ciclo de leitura no Oracle.
- **Parâmetros**:
  - `Default`: Limpa o cache de estado para forçar o reenvio de todos os erros.
  - `-KeepCache`: Mantém a lógica de delta (notifica apenas novos erros detectados).

---

## Operação e Diagnóstico

### Logs
- **Localização**: `Logs/Montagem.log`.
- **Camadas**: Identificadas pelos prefixos `[PS]` (PowerShell) e `[VBA]` (Excel).

### Matriz de Exit Codes
| Código | Significado |
| :--- | :--- |
| **0** | Sucesso absoluto |
| **4** | Falha técnica ao invocar a macro |
| **5** | Timeout: Processamento excedeu 300 segundos |
| **6** | Erro Fatal reportado pela lógica de negócio VBA |
| **7** | Workbook bloqueado para escrita (Read-Only) |
| **8** | Falha de compilação detectada no Preflight |

### Regras Críticas
1. **Idempotência**: O arquivo `Cache_Estado_Detalhado.txt` previne o spam de notificações, enviando alertas apenas quando mudanças significativas no estado de erro forem detectadas.
2. **Consistência de Dados**: O robô aborta imediatamente se o Refresh do Oracle falhar, protegendo a integridade da análise fiscal.
