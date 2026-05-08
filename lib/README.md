# Biblioteca PowerShell Compartilhada (`lib/`)

[⬅️ Voltar para o Hub Central](file:///c:/Automacoes/README.md)

Este diretorio contem os modulos e scripts utilitarios consumidos pelos orquestradores de automacao. Estes componentes formam a fundacao tecnica para a soberania e seguranca do hub.

## 📝 `Lib-Logging.psm1` (v1.3)

Modulo de logging centralizado e inteligencia operacional.

### Diferenciais Tecnicos:
- **`Base64 Bridge`**: Implementa a decodificacao automatica de logs vindos de Python ou Node.js (via prefixo `B64:`). Isso garante que acentos PT-BR nunca corrompam nos arquivos finais.
- **`Auto-Masking`**: Protege automaticamente e-mails, senhas e chaves de API, impedindo o vazamento de segredos nos logs.
- **`Pre-Flight Diagnostics`**: Fornece o motor `Test-AutomationPreFlight` para validacao de saude do ambiente (Disco, Oracle Ping, Paths).
- **`Traceability`**: Enforce o uso de `ExecId` para correlacao universal.

---

## 📧 `Lib-Email.psm1` (v1.2)

Interface de alta fidelidade para disparos via Outlook COM.

### Diferenciais Tecnicos:
- **`Outlook-Safe Protocol`**: O script **NUNCA** executa o comando `.Quit()`. Isso garante que o Outlook permaneca vivo e consiga esvaziar a *Outbox* (Caixa de Saida) de forma assincrona, evitando que e-mails fiquem presos.
- **Identidade Visual**: Captura automatica da assinatura oficial com imagens (CIDs) atraves do metodo `.Display()`.
- **Modo Teste**: Redirecionamento inteligente via variavel de ambiente `AUTOMACAO_TEST_EMAIL`.

---

## 💬 `Send-WhatsApp.ps1`

Wrapper PowerShell para o motor Node.js. Gerencia concorrencia e sessao (Pairing) do WhatsApp Web de forma transparente para os robos.

---

## 🧪 Testes de Qualidade (Pester)

Para garantir a resiliência industrial, a biblioteca conta com testes automatizados utilizando o framework **Pester**.

- **`tests\Lib-Logging.Tests.ps1`**: Valida o motor de logging, garantindo que o registro de eventos e o tratamento de erros estejam operantes antes do deploy em produção.

Execução recomendada:
```powershell
Invoke-Pester -Path ".\tests\Lib-Logging.Tests.ps1" -Output Detailed
```

---

## 🚀 Como Utilizar (Padrao Ouro)

Todo novo orquestrador deve seguir o padrao:

```powershell
# Importacao com Caminhos Dinamicos
$libLogging = Join-Path $projectRoot "lib\Lib-Logging.psm1"
Import-Module $libLogging -Force

# Pre-Flight (Obrigatorio)
if (-not (Test-AutomationPreFlight -ExecId $Id -CheckOracle)) { exit 9 }

# Envio de E-mail Blindado
Send-OutlookEmail -To "fiscal@empresa.com" -Subject "Alerta" -HtmlBody "<h1>Sucesso</h1>"
```

> **Nota de Engenharia:** Todo o codigo-fonte deve ser **ASCII-Safe**. Termos acentuados em logs devem ser evitados ou escapados, delegando a integridade linguistica ao protocolo Base64 em tempo de execucao.
