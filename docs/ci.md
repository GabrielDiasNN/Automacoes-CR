# CI — Estrutura, Regras e Operacao

Documento vivo da esteira de CI do monorepo. Complementa `docs/architecture-standard.md`.

## Camadas

A validacao acontece em tres camadas complementares:

1. **Pre-commit local** (`.githooks/pre-commit`): `Tools/ValidarAutomacoes.ps1 -OnlyGovernance -StagedOnly`.
2. **CI por PR/push** (`.github/workflows/governanca.yml`): jobs paralelos por area, com `Tools/ValidarAutomacoes.ps1` como orquestrador soberano da governanca estatica no job `governanca-agregada`.
3. **Seguranca agendada** (`.github/workflows/seguranca-agendada.yml`): toda segunda 09:00 UTC roda `pip-audit` (runtime) e gitleaks no historico completo; falhas abrem issue com label `seguranca`.

## Topologia do workflow Governanca

| Job (status check) | Runner | Quando roda |
|--------------------|--------|-------------|
| Gitleaks Security Scan | ubuntu | sempre |
| Preparar diff | ubuntu | sempre |
| Lint Python | ubuntu | diff contem `.py` ou `requirements*` |
| Testes Python | windows | diff contem `.py` ou `requirements*` |
| Testes E2E | windows | diff contem Python ou JS/HTML/CSS |
| Governanca agregada | windows | sempre (soberano) |
| Testes PowerShell (Pester) | windows | diff contem `.ps1/.psm1/.psd1` |
| Conformidade de log | windows | diff contem script PowerShell operacional |
| Lint JavaScript (Dashboard) | ubuntu | diff contem JS/HTML/CSS |
| Markdown | windows | diff contem `.md` |
| Resumo final | ubuntu | sempre (`always()`) — gate consolidado |

A selecao por area vem dos outputs de `Tools/Get-GovernanceTargetSummary.ps1`
(`HasPython`, `HasPowerShell`, `HasJs`, `HasMarkdown`). Em `full_scan`
(caminho critico alterado: `Tools/`, `lib/`, workflows, skills, etc.) ou diff
vazio, todas as areas sao forcadas.

## Severidade

- **Bloqueante (required checks)**: `Gitleaks Security Scan`, `Governanca agregada`, `Resumo final`. O `Resumo final` falha se qualquer job obrigatorio falhar ou for cancelado; jobs pulados por area contam como OK.
- **Nao bloqueante**: `pip-audit` no PR roda com `continue-on-error` (o gate real e o agendado semanal); warnings de ESLint nao falham o job.
- **Gate de cobertura**: `--cov-fail-under=77` nos testes Python (regressao; cobertura real medida em 80% em 12/06/2026 — ao subir a cobertura, suba o gate junto).
- **CHANGELOG**: PR com mudanca de codigo (`.py`, `.ps1/.psm1/.psd1`, `.js`, `.sql`, fora de testes/docs/CI) exige entrada no `CHANGELOG.md`. Override: incluir `[skip-changelog]` no titulo do PR.

## Validacao

### Ruleset da branch main

Configurado via API (exige `gh auth login` com escopo `repo`):

```bash
gh api repos/GabrielDiasNN/automacoes/rulesets -X POST --input - <<'EOF'
{
  "name": "protecao-main",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request", "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["squash", "merge"]
    } },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [
          { "context": "Gitleaks Security Scan" },
          { "context": "Governanca agregada" },
          { "context": "Resumo final" }
        ]
    } }
  ]
}
EOF
```

Conferir: `gh api repos/GabrielDiasNN/automacoes/rulesets`.

### Politica de pin de actions

Toda action e pinada pelo SHA do commit da versao, com comentario `# vX.Y.Z`
ao lado. Atualizacoes chegam exclusivamente via Dependabot (ecosistema
`github-actions`), que entende pins por SHA e mantem o comentario.

### Verificacao local antes do push

- YAML: `python -c "import yaml,io; yaml.safe_load(io.open('.github/workflows/governanca.yml',encoding='utf-8'))"` (ou `actionlint`, se instalado).
- Governanca completa: `./Tools/ValidarAutomacoes.ps1 -BasePath .`
- Pester: `Invoke-Pester -Path .\lib\tests -CI`
- Frontend (Dashboard React): `cd Dashboard; npm ci; npm run lint; npm run build`
- Cobertura: `$env:PYTHONPATH='Orchestrator'; pytest Orchestrator\tests -m "not e2e" --cov=app --cov=worker`

### Monitoramento de runs

`./Tools/Watch-CI.ps1` (ultimas runs do branch) ou
`./Tools/Watch-CI.ps1 -RunId <id> -Follow` (acompanhar ate concluir).
Baseline de duracao: `gh run list --workflow Governanca --json durationMs`.
