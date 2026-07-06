# Painel de Controle de Qualidade (Quality Dashboard)

> **Versão:** v1.0.0 | **Atualizado:** 05/07/2026

Este painel consolida as métricas de qualidade de software do **Hub de Automações** (v1.0.0). Ele é atualizado dinamicamente pelo script local de snapshot e auditado no pipeline de integração contínua (CI).

---

## 📈 Status Atual das Métricas (Snapshot 27/05/2026)

O quadro abaixo resume a conformidade da codebase do projeto em relação às metas estabelecidas na governança técnica:

| Métrica | Meta estabelecida | Valor Atual (Snapshot) | Status |
|---|---|---|---|
| **Cobertura de Testes (Pytest)** | `>= 60%` | **81%** | ✅ Meta Atingida |
| **Erros de Tipagem (Mypy)** | `0` | **0** | ✅ Meta Atingida |
| **Score de Estilo (Pylint)** | `>= 8.5/10` | **10/10** | ✅ Meta Atingida |
| **Tamanho Versionado (Git)** | `<= 150 MB` | **2.54 MB** | ✅ Meta Atingida |
| **Governança Agregada e ZeroTrust** | `APROVADO` | **APROVADO** | ✅ Meta Atingida |
| **Arquivos Grandes (> 5 MB)** | `0` (fora do `.gitignore`) | **0** | ✅ Meta Atingida |

---

## 🗃️ Detalhes e Métricas Auxiliares

*   **Tamanho do Código Fonte Limpo:** **9.83 MB** (totalizando **257 arquivos** de código-fonte úteis, excluindo `.git`, `.venv`, `.wwebjs_auth`, caches e logs).
*   **Pegada Operacional Local Excluída:** o snapshot separa explicitamente sessão local do WhatsApp em `lib/.wwebjs_auth/`, logs, banco SQLite/WAL e estados transitórios das automações para não contaminar a meta do payload versionado.
*   **Payload Versionado no Git:** a meta de tamanho passa a medir apenas o conteúdo efetivamente rastreado pelo Git, que é o artefato portátil e auditável do projeto.
*   **Zero Trust Scan:** O escaneamento local de chaves secretas e credenciais retornou 0 vulnerabilidades ativas em toda a base de código.
*   **Catálogo Governado:** O snapshot local agora também reporta cobertura de `automation.manifest.json`, runbooks presentes, automações com smoke declarado e issues abertas no catálogo.
*   **Baseline Operacional Live:** Quando a API local está online, o snapshot também consulta `GET /api/system/baseline` e informa o status consolidado `healthy`, `attention` ou `incident`, junto da ação recomendada.

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
6. A execução de toda a suite nativa de conformidade de governança local (`ValidarAutomacoes.ps1`);
7. A leitura opcional do baseline operacional live quando o Orchestrator está disponível na porta `8000`.

---

## ⏱️ Critério de Transição do Job `benchmark` (não-bloqueante)

O job `benchmark` do `.github/workflows/governanca.yml` (pytest-benchmark, 4
testes de performance baseline) roda com `continue-on-error: true` desde a
Fase 3 do plano de melhoria de QA (jun/2026) — resultados são publicados em
`benchmark-results.json`, mas uma regressão de performance não bloqueia o PR.

**Decisão (05/07/2026, planejamento de fechamento de desenvolvimento):**
mantido não-bloqueante por tempo indeterminado. Critério explícito para
reavaliar:
- Se algum dos 4 benchmarks (`test_bench_schedule_parse`,
  `test_bench_portfolio_catalog_build_summary`,
  `test_bench_oracle_extract_serialize_rows_1000`,
  `test_bench_system_diagnostics_build_payload`) apresentar uma regressão
  sustentada (não um outlier isolado) em 3 execuções consecutivas de CI, abrir
  uma revisão para decidir entre: (a) investigar e corrigir a causa raiz, ou
  (b) formalizar um novo baseline aceito.
- Só promover o job para bloqueante (`continue-on-error: false`) se houver um
  incidente real de produção rastreável a uma regressão de performance que o
  job já media e não bloqueou — até lá, o custo de falsos positivos (runners
  de CI compartilhados têm variância de timing) supera o benefício.
