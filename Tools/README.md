# Ferramentas de Manutenção (Tools)

Este diretório contém utilitários para garantir a governança, integridade e conformidade da Central de Automações.

## 🛠️ Ferramentas Ativas (Modernas)

### Governança e Testes (CI/CD Local)
- **Test-ZeroTrust.ps1:** Garante que nenhuma senha ou segredo esteja hardcoded.
- **Test-SqlPerformance.ps1:** Bloqueia o uso de `SELECT *` e valida queries.
- **Test-PythonGovernance.ps1:** Valida Type Hints e padrões Python.
- **Test-PowerShellGovernance.ps1:** Valida tipagem estrita em PS.
- **Test-PortablePaths.ps1:** Impede o uso de caminhos absolutos (`C:\...`).
- **Test-SourceEncoding.ps1:** Garante que os arquivos fonte estejam em UTF-8 sem corrupção.

### Operação e Utilitários
- **New-Automation.ps1:** Scaffold para criar novas automações no padrão ouro.
- **Open-LatestLog.ps1:** Atalho rápido para o log da última execução.
- **AplicarPoliticaRetencao.ps1:** Gestão de limpeza de logs e arquivos temporários.
- **ValidarAutomacoes.ps1:** Health check completo de todo o hub.

---

## 💾 Ferramentas de Legado (VBA)

Localizadas em `Tools/Legacy_VBA/`.
Estas ferramentas foram utilizadas durante o período de transição e agora servem apenas como referência para manipulação de arquivos XLSM e módulos `.bas` antigos.

> **Nota:** Não utilize estas ferramentas para novos desenvolvimentos.
