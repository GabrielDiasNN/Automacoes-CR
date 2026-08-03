# Hooks locais do agente

Fiação em [`.claude/settings.json`](../settings.json). Hooks são carregados no início da sessão — **alterar estes arquivos exige reiniciar o Claude Code**.

| Arquivo | Evento | Matcher | Bloqueia? |
|---|---|---|---|
| `Assert-FileEncoding.ps1` | `PostToolUse` | `Edit\|Write` | Sim (exit 2) |
| `Register-GateRun.ps1` | `PostToolUse` | `Bash\|PowerShell` | Não (async) |
| `Assert-StopQualityGate.ps1` | `Stop` | `*` | Sim (exit 2) |
| `HookCommon.psm1` | — | — | módulo compartilhado |

## Assert-FileEncoding.ps1

Valida o encoding do arquivo recém-escrito delegando para `Tools/Test-SourceEncoding.ps1`, que é a fonte única da regra (`.ps1`/`.psm1` com BOM; demais fontes sem BOM). Não reimplementa a checagem.

Por que `PostToolUse` e não `PreToolUse`: no `PreToolUse` o arquivo ainda não existe e o BOM não está no `content` — ele é decisão de quem grava, não do texto. Não há o que inspecionar. O `exit 2` devolve o stderr ao agente, o que é funcionalmente equivalente a bloquear.

Arquivos fora da raiz do repositório (scratchpad, `%TEMP%`) são ignorados.

## Register-GateRun.ps1

Grava carimbo de tempo em `.claude/.state/` (ignorado pelo git) ao detectar `pytest`, `ValidarAutomacoes`/`Test-PythonGovernance`/`Test-SourceEncoding` ou `npm run build|lint` no comando executado.

O marcador registra que o comando **foi disparado**, não que passou. A leitura da saída continua sendo obrigação do agente.

## Assert-StopQualityGate.ps1

Barra o encerramento da tarefa quando o trabalho pendente não passou pela verificação correspondente:

- `.py` sob `Orchestrator/`, `lib/python/` ou `Produção Beneficimento/src/` alterado sem marcador de `pytest` posterior ao mtime da edição;
- `Dashboard/src/` alterado sem marcador de lint/build posterior;
- qualquer arquivo pendente violando a regra de encoding.

Não roda o gate completo: `ValidarAutomacoes.ps1 -OnlyGovernance` foi medido em **171 s**, acima do timeout de hook e inviável a cada encerramento. A fonte final de verdade continua sendo o pre-commit hook e o CI.

Respeita `stop_hook_active` — sem isso, um bloqueio que o agente não consiga satisfazer vira laço infinito.

## Armadilha ao consumir ferramentas de `Tools/`

`Test-SourceEncoding.ps1` emite os achados via `Write-Host` e `Out-Host`, que escrevem no **host** e não no pipeline. Capturar com `2>&1` no mesmo processo devolve string vazia e perde exatamente o detalhe que interessa (`UTF8_BOM_FORBIDDEN` vs. `POWERSHELL_BOM_MISSING`).

`Invoke-EncodingCheck` (em `HookCommon.psm1`) resolve executando o verificador como **processo filho**, onde tudo converge para o stdout. Os caminhos trafegam por arquivo temporário, nunca interpolados na linha de comando — nome com aspas ou espaço não vira injeção de argumento.

## Testar sem reiniciar a sessão

```powershell
$env:CLAUDE_TOOL_INPUT = (@{ file_path = "C:\Automacoes\algum\arquivo.py" } | ConvertTo-Json -Compress)
& ".\.claude\hooks\Assert-FileEncoding.ps1"; "exit=$LASTEXITCODE"
$env:CLAUDE_TOOL_INPUT = $null
```
