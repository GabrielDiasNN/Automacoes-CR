# Central de Automações

Este diretório contém a estrutura centralizada para automações via Excel (VBA) e PowerShell.

## Estrutura de Pastas
- `MonitorAutomacoes.ps1`: Script principal que gerencia o agendamento e execução.
- `config.json`: Cadastro centralizado de todas as automações ativas.
- `_Template/`: Modelo base para criar novas automações.
- `Módulos/` (Receitas Bloqueadas, etc): Pastas individuais para cada processo.

## Como Adicionar uma Nova Automação
1.  **Copie a pasta `_Template`**: Dê o nome da sua nova automação à pasta copiada.
2.  **Adicione sua Planilha**: Coloque seu arquivo `.xlsm` dentro da nova pasta.
3.  **Configure o Disparador**: Edite o arquivo `Trigger_Automation.vbs` na nova pasta:
    - `excelPath`: Ajuste para o nome da sua planilha.
    - `macroName`: Nome da macro que deve ser chamada inicialmente.
    - `logPath`: Ajuste o nome do arquivo de log se desejar.
4.   **Cadastre no Monitor**: Abra o arquivo `C:\Automacoes\config.json` e adicione a nova tarefa no array `"tasks"`.
5.  **Reinicie o Monitor**: O monitor recarregará a configuração automaticamente em até 20 segundos.

## Padronização Necessária
- O arquivo principal de disparo deve sempre se chamar `Trigger_Automation.vbs`.
- Utilize a subpasta `Logs/` para os registros de execução.
- Se possível, retorne ExitCodes específicos para erros conhecidos.

---
*Mantido por Antigravity AI*
