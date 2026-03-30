# Padroes de Nomenclatura PowerShell

Este guia define como nomear funcoes PowerShell para manter consistencia e evitar avisos do Script Analyzer.

## Regra principal

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

## Regras praticas

- Use substantivos descritivos e especificos: `TaskProcess`, `ConfigHash`, `ComObjectReference`.
- Evite abreviacoes opacas em nomes de funcoes.
- Nao use verbos fora da lista oficial (`Get-Verb`) sem alinhamento do time.
- Para novos scripts, valide antes de commit com `Tools/Test-PowerShellApprovedVerbs.ps1`.

## Validacao automatica

O repositorio possui hook em `.githooks/pre-commit` que executa duas validacoes em arquivos PowerShell staged:

- Nome de funcao no formato `Verbo-Substantivo` (com hifen)
- Verbo dentro da lista oficial do PowerShell (`Get-Verb`)

Ative localmente com:

```bash
git config core.hooksPath .githooks
```
