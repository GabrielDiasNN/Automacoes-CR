---
name: automacao-standard
description: Use esta skill para criar ou modificar automações no projeto Automacoes, garantindo padronização de VBS, Excel/VBA e definição clara de canais de saída (WhatsApp/Email).
---

# Padrão de Desenvolvimento de Automações

## Objetivo
Garantir que toda nova automação ou modificação siga a arquitetura **VBS → Excel/VBA → Notificação**, com tratamento de erro e logging padronizados. O ponto de entrada é sempre o `Trigger_Automation.vbs` baseado no **Template Universal v3.0**.

## Definição de Saída (Scope)
Ao iniciar uma tarefa, identifique os canais de comunicação necessários:
- **WhatsApp**: Ative `POST_EXECUTION_BAT` no VBS apontando para `RunWhatsApp.bat`.
- **Email**: Implemente a macro VBA interagindo com `Outlook.Application`.
- **Híbrido**: Ambos.
- **Relatório**: Apenas execução de cálculos/arquivos, sem envio externo.

## Componentes Obrigatórios
1. **`Trigger_Automation.vbs`** (baseado em `_Template`): Ponto de entrada. Gerencia Excel, executa macro e captura erros fatais.
2. **`Logs/Execution.log`**: Toda automação deve ter sua pasta `Logs` local com este arquivo.
3. **Idempotência**: O script deve poder ser reiniciado sem duplicar envios ou corromper dados.

## Template Universal v3.0 — Feature Flags
Ao copiar o `_Template\Trigger_Automation.vbs`, configure as flags no cabeçalho:

```vbscript
' ========== CONFIGURACOES DO MODULO ==========
excelPath = "C:\Automacoes\NomePasta\Arquivo.xlsm"
macroName = "NomeDaMacro"
logPath   = "C:\Automacoes\NomePasta\Logs\Execution.log"

' [Flag] Monitoramento assíncrono via Log VBA (Robo Fiscal / Timeout)
USE_TIMEOUT_MONITOR = False       ' True para módulos com macro longa
vbaLogPath          = "C:\Automacoes\NomePasta\Logs\VBA_Internal.log"
maxTimeoutSeconds   = 300

' [Flag] Script pós-macro (BAT/Node.js)
POST_EXECUTION_BAT  = ""          ' Ex: "C:\Automacoes\NomePasta\RunWhatsApp.bat"
```

### Quando usar cada flag:
| Módulo | `USE_TIMEOUT_MONITOR` | `POST_EXECUTION_BAT` |
|---|---|---|
| Simples (ex: Receitas Emitidas) | `False` | `""` |
| Robo Fiscal (ex: Montagem) | `True` | `""` |
| WhatsApp Bridge (ex: Receitas Bloqueadas) | `False` | Caminho do `.bat` |

## Passo a Passo para Novas Automações
1. Copie a pasta `_Template` e renomeie para o nome do módulo.
2. Configure o cabeçalho do `Trigger_Automation.vbs` com os caminhos e flags corretos.
3. No Excel (`.xlsm`), crie a macro principal (ex: `ExecutarProcesso`).
4. Se **WhatsApp**: configure `whatsapp-config.json` e garanta que `RunWhatsApp.bat` existe.
5. Se **Email**: implemente a verificação do anexo via `Dir()` ou `FSO` antes do envio.
6. Adicione a tarefa no `config.json` da raiz seguindo o schema da skill `automacao-monitor`.

## Regras de Ouro
- **`DisplayAlerts = False`** e **`Visible = False`** sempre.
- **`ScreenUpdating = False`** e **`EnableEvents = False`**: reduz interferências externas.
- **`AskToUpdateLinks = False`**: evita pop-ups ao abrir planilhas com links externos.
- **Cleanup garantido**: O bloco `LimparObjetosExcel()` fecha o processo mesmo em caso de erro.
- **`On Error GoTo 0`**: sempre restaurar o handler após blocos `On Error Resume Next`.
