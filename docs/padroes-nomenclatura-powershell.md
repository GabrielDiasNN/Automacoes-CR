# Padroes de Nomenclatura e Governanca PowerShell

Este guia define como escrever scripts PowerShell para manter consistencia, evitar avisos do Script Analyzer e aderir as regras globais de estabilidade.

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

## Tipagem Estrita e Excecoes (Mandatorio)

Conforme as diretrizes globais (SKILL: `powershell-automation-monitor`), o PowerShell neste projeto DEVE:
1. **Tipagem Explicita**: Parametros e variaveis devem declarar seu tipo (`[string]`, `[int]`, `[hashtable]`).
2. **Tratamento Nominal de Excecoes**: E proibido usar capturas genericas de erro (`catch { ... }`). O bloco catch deve ser especifico para a excecao esperada (ex: `catch [System.IO.IOException] { ... }`).

## Regras praticas

- Use substantivos descritivos e especificos: `TaskProcess`, `ConfigHash`, `ComObjectReference`.
- Evite abreviacoes opacas em nomes de funcoes.
- Nao use verbos fora da lista oficial (`Get-Verb`) sem alinhamento do time.
- Para novos scripts, valide antes de commit com as ferramentas em `Tools/`.

## Validacao automatica

O repositorio possui hook em `.githooks/pre-commit` e CI que executa validacoes em arquivos PowerShell staged:

- Nome de funcao no formato `Verbo-Substantivo` e verbo aprovado (`Tools/Test-PowerShellApprovedVerbs.ps1`)
- Avaliacao de qualidade via PSScriptAnalyzer e restricao de `try/catch` generico (`Tools/Test-PowerShellGovernance.ps1`)

Ative os hooks localmente com:

```bash
git config core.hooksPath .githooks
```
