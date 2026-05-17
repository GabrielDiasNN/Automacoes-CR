# Padroes de Nomenclatura e Governanca PowerShell

Este documento e um guia rapido para colaboradores.
As fontes canonicas de regra continuam sendo:
- `.github/skills/powershell-automation-monitor/SKILL.md`
- `Tools/Test-PowerShellApprovedVerbs.ps1`
- `Tools/Test-PowerShellGovernance.ps1`

## Regra principal de Nomenclatura

Use sempre o formato `Verbo-Substantivo` em PascalCase:

- Bom: `Get-ConfigHash`
- Bom: `Start-Automacao`
- Bom: `Remove-ComObjectReference`
- Evitar: `Run-Automacao`
- Evitar: `Release-ComObject`
- Evitar: `Sanitize-FileName`

## Verbos recomendados no projeto

- Leitura e consulta: `Get`, `Test`
- Escrita e alteracao: `Set`, `Add`, `Update`, `Remove`
- Execucao de processos: `Start`, `Stop`, `Invoke`
- Importacao e exportacao: `Import`, `Export`
- Conversao: `ConvertTo`, `ConvertFrom`

## Tipagem e Excecoes (Mandatorio)

Conforme a skill canônica `powershell-automation-monitor`, os scripts operacionais devem:
1. Usar `[CmdletBinding()]` e `param(...)` quando houver interface publica.
2. Tipar parametros relevantes e manter fluxo de falha controlada.
3. Evitar `catch` generico quando houver excecao esperada identificavel.

## Regras praticas

- Use substantivos descritivos e especificos: `TaskProcess`, `ConfigHash`, `ComObjectReference`.
- Evite abreviacoes opacas em nomes de funcoes.
- Nao use verbos fora da lista oficial (`Get-Verb`) sem alinhamento do time.
- Para novos scripts, valide antes de commit com as ferramentas em `Tools/`.
- Em conflito entre este guia e as fontes canonicas, prevalecem as fontes canonicas.

## Validacao automatica

O repositorio possui hook em `.githooks/pre-commit` e CI que executa validacoes em arquivos PowerShell staged:

- Nome de funcao no formato `Verbo-Substantivo` e verbo aprovado (`Tools/Test-PowerShellApprovedVerbs.ps1`)
- Avaliacao de qualidade via PSScriptAnalyzer e restricao de `try/catch` generico (`Tools/Test-PowerShellGovernance.ps1`)

Ative os hooks localmente com:

```bash
git config core.hooksPath .githooks
```
