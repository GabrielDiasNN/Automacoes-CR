# Automação - Montagem de Terceirizados (Robô Fiscal v8.8.0)

## Visão Geral

Este projeto automatiza a validação fiscal determinística de ordens de montagem externa. O foco é garantir o cruzamento preciso entre Notas Fiscais (NF) e Ordens de Fabricação (OBs) de terceirizados, notificando divergências à equipe fiscal.

## Fluxo do Processo

`MonitorAutomacoes.ps1` (Orquestrador) -> `run.ps1` (Runner PS) -> `Excel COM` (VBA) -> `Oracle DB` -> `Email Outlook`

---

## Componentes do Projeto

### 1. Orquestrador PowerShell (`run.ps1`)
Gerencia a execução da automação:
- Inicia Excel em modo oculto.
- **Preflight VBA**: Valida se o projeto VBA está compilável antes de iniciar.
- **Monitoramento via Log**: Captura o baseline do arquivo de log e aguarda a mensagem `FIM DO PROCESSO.` com o status de sucesso.
- **Tratamento de Erros**: Converte falhas de COM, VBA ou Timeout em exit codes operacionais padronizados.

### 2. Workbook Fiscal (`Validador_Notas_Montagem.xlsm`)
Inteligência central do robô:
- **Refresh Deterministico**: Verifica a coluna `VALIDA_ATUALIZACAO` no Oracle para confirmar que os dados foram renovados antes do processamento.
- **Validação NF/OB**: Lógica complexa em VBA que cruza saldos e quantidades.
- **Notificação**: Gera e envia e-mails HTML dinâmicos via Outlook.

### 3. Utilitário de Reenvio (`ReenviarAlertaErros.ps1`)
Script para situações excepcionais:
- Permite reenviar os alertas de erro detectados na última execução sem processar novamente o Oracle.
- **Uso**: `pwsh -File ReenviarAlertaErros.ps1` (limpa cache) ou `-KeepCache` (mantém delta).

---

## Operação e Manutenção

### Logs e Diagnóstico
- **Log Unificado**: `Logs/Montagem.log`.
  - Prefixos: `[PS]` (PowerShell) e `[VBA]` (Excel).

### Códigos de Saída (Exit Codes)
- `0`: Sucesso.
- `4`: Falha ao invocar macro.
- `5`: Timeout (VBA não respondeu em 300s).
- `6`: VBA reportou erro fatal ou falha de negócio.
- `7`: Workbook bloqueado (somente leitura).
- `8`: Falha de compilação VBA.

### Regras de Negócio Críticas
1. **Idempotência de Notificação**: O robô utiliza um cache (`Cache_Estado_Detalhado.txt`) para evitar notificar o mesmo erro repetidamente, disparando e-mail apenas se houver novos erros ou mudanças no estado.
2. **Segurança Fiscal**: Em caso de falha no Refresh do Oracle, a automação aborta para evitar falsos positivos com dados obsoletos.
