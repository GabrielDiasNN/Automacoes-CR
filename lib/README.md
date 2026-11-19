# Biblioteca Compartilhada (`lib/`)

[⬅️ Voltar para o Hub Central](../README.md)

Este diretório contém os módulos PowerShell, drivers Node.js e o núcleo Python compartilhado consumidos pelos runners de automação, scripts de infraestrutura e CLIs operacionais.

## 🐍 Núcleo Python dos Runners (`lib/python/`)

- **`hub_runner.py`**: orquestração comum das automações (`run_*.py` e `_Template/run_template.py`) — lock global por mutex (`AutomationMutex`), pré-flight (disco, caminhos e fila Oracle), passos Python com retry (`run_python_step`), telemetria (`HttpTelemetryClient`), idempotência por canal (`delivery_state.json`), rotação de logs JSONL sem BOM (`rotate_log`) e escrita atômica.
- **`hub_whatsapp.py`**: leitura de manifesto/configuração, normalização de destino, gravação do lote para o motor WhatsApp e reconciliação de entrega.
- **`obs_cards_runner.py`**: motor comum dos runners de cards (`OFST-06` e `ORB-07`).

---

## 📝 `Lib-Logging.psm1`

Módulo PowerShell focado nos consumidores de infraestrutura (`Infrastructure/MonitorAutomacoes.ps1` e `lib/Lib-Email.psm1`):

- **`Protect-SensitiveData`**: mascara automaticamente e-mails, credenciais rotuladas e hosts de strings de conexão Oracle nos logs (paridade textual com `lib/python/log_masking.py`).
- **`Write-AutomacaoLog`**: grava linha JSONL mascarada em UTF-8 sem BOM e imprime no console.

> **Encoding:** UTF-8 ponta a ponta em toda a biblioteca (`.ps1`/`.psm1` em UTF-8 com BOM; logs `.jsonl` e saída Python/Node em UTF-8 sem BOM).

---

## 🚨 `Lib-Retry.psm1` & 📧 `Lib-Email.psm1`

- **`Lib-Retry.psm1`**: expõe `Send-AlertaFalhaDefinitiva`, acionado via CLI `lib/Invoke-OutlookEmail.ps1` quando uma automação esgota tentativas.
- **`Lib-Email.psm1`**: interface para disparos via Outlook COM (preserva a sessão do Outlook aberta para esvaziar a Outbox de forma assíncrona, captura assinatura oficial e respeita `AUTOMACAO_TEST_EMAIL` no escopo User).

---

## 💬 WhatsApp (`Send-WhatsApp.ps1`, `Lib-WhatsAppBatch.psm1`, `whatsapp-daemon.js`)

- **`Send-WhatsApp.ps1`**: wrapper PowerShell para o motor Node.js (`WhatsApp-Core.js`) e o cliente HTTP do daemon (`Lib-WhatsAppBatch.psm1`), com isolamento de ambiente por allowlist no `Start-WhatsAppDaemon.ps1` e limpeza segura de processos órfãos.

---

## 📦 Dependências Node do motor WhatsApp (`package.json`)

O `postinstall` aplica `lib/patches/*.patch` por `scripts/aplicar-patches.js` (sem dependências e idempotente), no lugar do `patch-package`. `extract-zip` usa o fork vendorizado em `lib/vendor/extract-zip` (`2.0.2-automacoes.1`, com as correções de CVE-2026-19693 e CVE-2026-56876). O procedimento de regeneração do lock e a guarda de dependências estão em `lib/CLAUDE.md`.

**Pendência operacional:** o `lib/node_modules` instalado nesta máquina continua com a árvore antiga. Produção só passa a usar as novas dependências depois de `npm ci` em `lib/`, com o canal WhatsApp em janela de manutenção.

---

## 🧪 Testes de Qualidade (Pester)

Para executar a suíte de testes PowerShell dos módulos ativos de `lib/`:

```powershell
Invoke-Pester -Path ".\lib\tests\Lib-Logging.Tests.ps1", ".\lib\tests\Lib-Retry.Tests.ps1", ".\lib\tests\Lib-WhatsAppBatch.Tests.ps1" -Output Detailed
```
