# Diretrizes de Governança do Repositório (Hub de Automações)

> **Versão:** v7.0.0 | **Atualizado:** 20/05/2026

Este documento estabelece as regras e padrões de integridade do Hub de Automações (v7.0.0), garantindo consistência técnica, segurança e idempotência operacional entre desenvolvedores e agentes autônomos (ChatGPT/Codex, Gemini CLI e Antigravity).

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

## 4. Pipeline de CI/CD (GitHub Actions)

O pipeline configurado em `.github/workflows/governanca.yml` é executado a cada push e pull request direcionados às ramificações protegidas, garantindo um "Quality Gate" implacável:

1.  **Gitleaks Security Scan:** Execução paralela da action oficial do Gitleaks para bloquear qualquer commit que contenha senhas, tokens ou chaves secretas (Zero Trust).
2.  **Configuração de Python e Cache:** Setup automatizado de Python 3.12 com cache de dependências `pip` ativado para otimizar o tempo de build.
3.  **Instalação de Lockfiles:** O pipeline instala as dependências estritas a partir de `requirements.txt`, `requirements-dev.txt` e `requirements-test.txt`.
4.  **Static Analysis & Style Checks:** Execução automática do Black, Isort, Mypy e Pylint. Qualquer aviso crítico ou erro quebra o pipeline.
5.  **Testes Automatizados (Pytest & Pester):** Execução obrigatória das suites de testes unitários para Python e PowerShell.
