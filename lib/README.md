# Biblioteca PowerShell Compartilhada (`lib/`)

Este diretório contém os módulos e scripts utilitários consumidos pelos orquestradores de automação.

## 📝 `Lib-Logging.psm1`

Módulo de logging centralizado. Garante que todas as automações gerem logs em formato compatível com o **Monitor de Automações** e o **Dashboard**.

### Principais Funções:
- **`New-ExecId`**: Gera um ID de execução único baseado em timestamp e aleatoriedade.
- **`Write-AutomacaoLog`**: Registra mensagens em formato padronizado:
  - `[dd/MM/yyyy HH:mm:ss] [PS] [LEVEL] [ExecId] mensagem`.
- **`Get-AutomacaoLogPath`**: Gera o caminho canônico do log mensal em `Logs/yyyy-MM_Slug.log`.
- **`Invoke-LogRotation`**: Limpa logs antigos baseados na janela de retenção configurada.

---

## 💬 `Send-WhatsApp.ps1`

Wrapper PowerShell para o bridge Node.js (`sendWhatsApp.js`). Fornece uma interface PowerShell limpa para envio de mensagens via WhatsApp Business.

### Modos de Execução:
- **`AUTO`**: Execução em segundo plano. Requer sessão autenticada. Se a sessão estiver corrompida, relança automaticamente em modo `PAIRING`.
- **`PAIRING`**: Abre uma janela CMD visível para o pareamento manual (escaneamento de QR Code).

### Parâmetros:
- `-ExecId`: ID da execução atual para rastreabilidade de log.
- `-Mode`: `AUTO` ou `PAIRING`.
- `-BaseDir`: Pasta da automação onde estão os arquivos `whatsapp-config.json` e `sendWhatsApp.js`.

---

## 📧 `Lib-Email.psm1`

Utilitários para gerenciamento e disparo de e-mails via Outlook COM.

### Principais Recursos:
- **Encapsulamento de Anexos**: Tratamento robusto de arquivos travados por outros processos.
- **Formatação HTML**: Helpers para construção de corpos de e-mail dinâmicos.

---

## 🚀 Como Utilizar em um Novo Projeto

Para garantir a integração com o Monitor, sempre importe a biblioteca de logging no início do seu script `run.ps1`:

```powershell
$libPath = "C:\Automacoes\lib\Lib-Logging.psm1"
Import-Module $libPath -Force

# Usando o logging padronizado
Write-AutomacaoLog -Message "Iniciando processamento" -Level "INFO" -ExecId $ExecId -LogPath $LogFile
```
