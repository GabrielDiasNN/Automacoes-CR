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

---

## 📧 `Lib-Email.psm1`

Utilitários para gerenciamento e disparo de e-mails via Outlook COM.

### Diferenciais Técnicos:
- **Identidade Visual**: Suporta a captura automática da **assinatura local** (com imagens/CIDs) e herança de **fontes da sessão** do usuário através do método `.Display()` preventivo.
- **Injeção de Conteúdo**: Permite inserir HTML dinâmico preservando o corpo original da mensagem (assinatura).
- **Encapsulamento de Anexos**: Tratamento robusto de arquivos travados por outros processos.

---

## 🚀 Como Utilizar em um Novo Projeto

Siga o padrão da arquitetura nativa:

```powershell
# Importação
Import-Module "C:\Automacoes\lib\Lib-Logging.psm1" -Force
Import-Module "C:\Automacoes\lib\Lib-Email.psm1" -Force

# Envio Nativo (Com Assinatura e Fonte do Outlook)
Send-OutlookEmail -To "alguem@empresa.com" -Subject "Assunto" -HtmlBody "<h1>Relatório</h1>"
```
