# Painel de Controle de Qualidade (Quality Dashboard)

> **Versão:** v7.0.0 | **Atualizado:** 2026-05-20

Este painel consolida as métricas de qualidade de software do **Hub de Automações** (v7.0.0). Ele é atualizado dinamicamente pelo script local de snapshot e auditado no pipeline de integração contínua (CI).

---

## 📈 Status Atual das Métricas (Snapshot 20/05/2026)

O quadro abaixo resume a conformidade da codebase do projeto em relação às metas estabelecidas na governança técnica:

| Métrica | Meta estabelecida | Valor Atual (Snapshot) | Status |
|---|---|---|---|
| **Cobertura de Testes (Pytest)** | `>= 60%` | **75%** | ✅ Meta Atingida |
| **Erros de Tipagem (Mypy)** | `0` | **0** | ✅ Meta Atingida |
| **Score de Estilo (Pylint)** | `>= 8.5/10` | **8.51/10** | ✅ Meta Atingida |
| **Tamanho do Repositório (Total)** | `<= 150 MB` | **96.97 MB** | ✅ Meta Atingida |
| **Governança Agregada e ZeroTrust** | `APROVADO` | **APROVADO** | ✅ Meta Atingida |
| **Arquivos Grandes (> 5 MB)** | `0` (fora do `.gitignore`) | **0** | ✅ Meta Atingida |

---

## 🗃️ Detalhes e Métricas Auxiliares

*   **Tamanho do Código Fonte Limpo:** **26.14 MB** (totalizando **241 arquivos** de código-fonte dinâmico e rastreado no git, excluindo `.git`, `.venv`, `.wwebjs_auth` e arquivos de logs).
*   **Arquivos Grandes Excluídos Legitimamente (Ignorados no Git):**
    *   Arquivos de persistência de sessão do WhatsApp (`lib/.wwebjs_auth/`): Caches grandes do motor Chromium (~200+ MB), devidamente protegidos no `.gitignore`.
    *   Banco de dados operacional local (`Orchestrator/automacoes.db`): Armazenamento relacional dinâmico de execuções (~22 MB), protegido no `.gitignore`.
*   **Zero Trust Scan:** O escaneamento local de chaves secretas e credenciais retornou 0 vulnerabilidades ativas em toda a base de código.

---

## 🛠️ Como Atualizar o Snapshot de Qualidade Localmente

Para re-executar todas as análises e coletar as métricas mais recentes de forma automatizada no ambiente Windows, execute o comando abaixo no console do PowerShell:

```powershell
powershell.exe -ExecutionPolicy Bypass -File Tools/Get-QualitySnapshot.ps1
```

O script fará de forma totalmente idempotente e segura:
1. A medição de arquivos e pastas reais;
2. A varredura de arquivos volumosos;
3. O cálculo da cobertura de código com `pytest-cov`;
4. A análise estática de conformidade e score do `Pylint`;
5. O type-checking do `Mypy` em todos os módulos ativos do Orquestrador;
6. A execução de toda a suite nativa de conformidade de governança local (`ValidarAutomacoes.ps1`).
