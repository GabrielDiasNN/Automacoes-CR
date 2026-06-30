# Diretrizes de Governança do Repositório (Hub de Automações)

> **Versão:** v9.5.0 | **Atualizado:** 27/05/2026

Este documento estabelece as regras e padrões de integridade do Hub de Automações (v9.5.0), garantindo consistência técnica, segurança e idempotência operacional entre desenvolvedores e agentes autônomos (ChatGPT/Codex, Gemini CLI e Antigravity).

---

## 1. Soberania de Encoding

**REGRAS ABSOLUTAS DE CODIFICAÇÃO:**
*   **PowerShell (`.ps1`, `.psm1`):** DEVEM ser codificados obrigatoriamente como `UTF-8 with BOM`. O motor legada do PowerShell 5.1 não interpreta acentuação nativa em UTF-8 sem BOM, o que corrompe strings de log e provoca erros fatais no Orquestrador.
*   **Outros Arquivos (`.py`, `.txt`, `.json`, `.md`, `.sql`, `.yml`):** DEVEM ser codificados como `UTF-8` (sem BOM).
*   **Documentação em Português (PT-BR):** Arquivos `.md` devem preservar acentuação nativa normal em Português do Brasil. É proibido usar ASCII empobrecido ou introduzir mojibakes.

---

## 2. Gestão de Dependências

O projeto utiliza o ecossistema `pip-tools` para garantir dependências 100% reprodutíveis e livres de drifts no ambiente local e no pipeline de CI.

*   **Arquivos de Entrada (`.in`):** Declaram apenas os pacotes de alto nível e suas restrições principais.
    *   `requirements.in` — Dependências de runtime do produto.
    *   `requirements-dev.in` — Ferramentas de linting, formatação e governança local.
    *   `requirements-test.in` — Suite de testes e drivers do Pytest.
*   **Lockfiles de Produção (`.txt`):** Gerados a partir do comando `pip-compile` no terminal, contendo as versões exatas e hashes de segurança travados.
    *   *Nunca edite os arquivos `.txt` diretamente.* Qualquer alteração deve ocorrer no arquivo `.in` correspondente, seguida da re-compilação:
        ```powershell
        .venv\Scripts\python.exe -m piptools compile requirements.in
        ```

---

## 3. Estilo e Qualidade de Código (Python)

Toda a codebase Python segue a governança descrita na skill canônica `.github/skills/python-enterprise-standard/SKILL.md`.

*   **Tipagem Estrita:** Uso obrigatório de `mypy --strict`.
*   **Análise Estática:** Qualidade garantida por `pylint`.
*   **Formatação e Imports:** Código garantido por `black` e `isort`.

**Validação Local:**
Antes de qualquer commit, os arquivos Python podem ser validados localmente através do validador corporativo:
```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PythonGovernance.ps1 -RootPath .
```

---

## 4. Topologia de Governança Local e Remota

### Padrão arquitetural

O contrato arquitetural oficial vive em `docs/architecture-standard.md` e é validado por `Tools/Test-ArchitectureStandard.ps1`. O v1 do validador falha apenas violações críticas, como quebra de snapshot-first em routers, persistência fora da camada autorizada ou automações com `run.ps1` sem manifesto governado, mantendo avisos para desvios que exigem maturação gradual.

### Pre-commit local

O hook `.githooks/pre-commit` não tenta espelhar todo o CI. Ele atua como barreira local rápida e seletiva, delegando a orquestração para `Tools/ValidarAutomacoes.ps1 -OnlyGovernance -StagedOnly`.

Contrato atual do hook:

1. **Diff staged como entrada:** o classificador compartilhado `Tools/Get-GovernanceTargetSummary.ps1` decide se o commit pode ser validado por caminhos staged ou se precisa escalar para varredura completa.
2. **Escalonamento por criticidade:** alterações em `Tools/`, `lib/`, contratos centrais, workflow, hook, skills ou `.gitleaks.toml` forçam scan completo de governança estática para evitar regressão em cadeia.
3. **Conformidade de log seletiva:** quando o diff staged altera `.ps1`/`.psm1` operacionais fora de `Tools/` e `Audit/`, a verificação de `Test-LogConformidade.ps1` roda localmente apenas nesses alvos.
4. **Objetivo:** bloquear regressões óbvias cedo, sem transformar todo commit em réplica do pipeline remoto.
5. **Resumo operacional local:** ao final de cada execução, `Tools/ValidarAutomacoes.ps1` publica o modo de seleção (`targeted_paths`, `full_scan` ou `no_paths`) e o tempo por etapa do ciclo local, facilitando a identificação de gargalos de produtividade sem relaxar a cobertura.

### GitHub Actions

O workflow `.github/workflows/governanca.yml` continua sendo o gate autoritativo e observável do repositório:

1. **Gitleaks Security Scan:** execução paralela da action oficial do Gitleaks para bloquear qualquer commit que contenha senhas, tokens ou chaves secretas (Zero Trust).
2. **Preparação do diff governado:** o job `preparar-diff` usa o mesmo classificador compartilhado do hook para publicar `selection_mode`, caminhos críticos e alvos de `conformidade-log`.
3. **Governança completa:** o job `governanca` instala dependências, valida formatação e análise estática, roda a governança agregada e executa suites Python e PowerShell.
4. **Conformidade de log condicional:** o job `conformidade-log` só roda quando o diff contém scripts PowerShell operacionais elegíveis; quando não houver alvo, ele será pulado por contrato.
5. **Markdown:** o job `markdown` mantém observabilidade separada para o padrão documental.

### Leitura correta do estado

- `pre-commit` verde significa que o diff local passou pela barreira rápida adequada ao seu escopo.
- `governanca.yml` verde significa que o repositório passou pelo gate completo.
- `conformidade-log` em branco não significa desativação; significa que o diff não continha alvos elegíveis para esse check.
