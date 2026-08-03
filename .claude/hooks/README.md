# Hooks locais do agente

Fiação em [`.claude/settings.json`](../settings.json). Hooks são carregados no início da sessão — **alterar estes arquivos exige reiniciar o Claude Code**.

| Arquivo | Evento | Matcher | Bloqueia? |
|---|---|---|---|
| `Assert-FileEncoding.ps1` | `PostToolUse` | `Edit\|Write` | Sim (exit 2) |
| `Assert-SensitiveWriteGuard.ps1` | `PreToolUse` | `Bash\|PowerShell` | Sim (exit 2) |
| `Register-GateRun.ps1` | `PostToolUse` | `Bash\|PowerShell` | Não (async) |
| `Assert-StopQualityGate.ps1` | `Stop` | `*` | Sim (exit 2) |
| `HookCommon.psm1` | — | — | módulo compartilhado |

## `exit $LASTEXITCODE` não é opcional na fiação

O `settings.json` invoca estes scripts como `pwsh -Command "& '<script>'"`. Nessa
forma o `exit 2` do script **não** chega ao harness: quando o script escreve em
stderr, o processo termina com **1**, que o Claude Code trata como erro comum e
descarta. O gate emite a mensagem certa e não bloqueia nada.

| Invocação | Código visto pelo harness |
|---|---|
| `-Command "& '<script>'"` | `1` — gate inerte |
| `-Command "& '<script>'; exit $LASTEXITCODE"` | `2` — bloqueia |
| `-File <script>` | `2` — bloqueia |

Por isso **todo** comando que invoca um script daqui termina com
`; exit $LASTEXITCODE` — inclusive `Register-GateRun.ps1`, que hoje é `async` e
sempre sai 0. Ali o sufixo não muda nada em operação normal; existe para que o
script não vire gate silenciosamente inerte se algum dia passar a bloquear, e
para que a fiação não tenha duas convenções concorrentes.

Ao adicionar um hook novo, **teste o código de saída pela fiação real**, não só
rodando o script direto: os dois caminhos divergem.

## Assert-FileEncoding.ps1

Valida o encoding do arquivo recém-escrito delegando para `Tools/Test-SourceEncoding.ps1`, que é a fonte única da regra (`.ps1`/`.psm1` com BOM; demais fontes sem BOM). Não reimplementa a checagem.

Por que `PostToolUse` e não `PreToolUse`: no `PreToolUse` o arquivo ainda não existe e o BOM não está no `content` — ele é decisão de quem grava, não do texto. Não há o que inspecionar. O `exit 2` devolve o stderr ao agente, o que é funcionalmente equivalente a bloquear.

Arquivos fora da raiz do repositório (scratchpad, `%TEMP%`) são ignorados.

## Assert-SensitiveWriteGuard.ps1

Fecha a lacuna do guard inline de `Edit|Write` do `settings.json`, que só cobre as
ferramentas de edição: um `Set-Content .env` disparado pelo shell passava por fora.

Bloqueia **escrita**, não leitura — ler `.env` é operação legítima e documentada
(o `CLAUDE.md` manda ler `ORCHESTRATOR_API_KEY` de lá). Exige verbo de escrita
**e** alvo sensível no mesmo segmento do comando (separadores: `;`, `&&`, `||`,
`|`, quebra de linha); sem isso, `Get-Content .env | Set-Content saida.txt` seria
barrado por engano. O conteúdo de `-Value`/`-Body` é descartado antes da análise,
senão citar `orchestrator.pid` dentro de um texto viraria bloqueio.

Erra para o lado conservador: na dúvida bloqueia, com a mensagem indicando o
segmento culpado. O caso conhecido é **texto que cita um comando**: uma mensagem
de `git commit` ou um trecho de documentação que mencione o cmdlet e o arquivo na
mesma linha é barrado, ainda que nada seja escrito. Descartar `-Value`/`-Body`
cobre o cmdlet; texto livre não tem marcador que permita distingui-lo de um
comando real. Contorne reformulando a frase — não enfraqueça o padrão.

A detecção é **textual**: alvo montado dinamicamente ou alcançado por glob não é
reconhecido. O guard reduz o alcance de um engano, não substitui permissão de
arquivo — não o trate como fronteira de segurança rígida. A lista de alvos é a mesma do guard de `Edit|Write` e os dois
precisam ser mantidos em sincronia manual.

## Register-GateRun.ps1

Grava carimbo de tempo em `.claude/.state/` (ignorado pelo git) ao detectar `pytest`, `ValidarAutomacoes`/`Test-PythonGovernance`/`Test-SourceEncoding` ou `npm run build|lint` no comando executado.

O marcador registra que o comando **foi disparado**, não que passou. A leitura da saída continua sendo obrigação do agente.

## Assert-StopQualityGate.ps1

Barra o encerramento da tarefa quando o trabalho pendente não passou pela verificação correspondente:

- arquivos de `git status --porcelain` reprovando em `ValidarAutomacoes.ps1 -OnlyGovernance -Paths` (os 14 checks: zero-trust, SQL, mypy/pylint, PSScriptAnalyzer, encoding, JSON, Playwright, manifesto, arquitetura, datas, semântica, Node);
- `.py` sob `Orchestrator/`, `lib/python/` ou `Produção Beneficimento/src/` alterado sem marcador de `pytest` posterior ao mtime da edição;
- `Dashboard/src/` alterado sem marcador de lint/build posterior.

Os dois últimos existem porque o gate de governança **não** roda pytest nem build do Dashboard.

### Por que `-Paths` não é opcional

| Modo | Custo |
|---|---|
| `-OnlyGovernance` sem alvos (`full_scan`) | **171 s** |
| `-OnlyGovernance -Paths <alterados>` | **6–9 s**; 18 s com dois `.py` (mypy) |

Mesmos 14 checks, ~28× de diferença. O timeout no `settings.json` é 240 s por margem. A fonte final de verdade continua sendo o pre-commit hook e o CI.

### Filtragem da saída

Mesmo reprovando, o gate emite 60+ linhas de `[OK]`. `Select-FailureLines` retém as linhas de `[ERRO]`/`[FALHA]` e o detalhe indentado que as segue — 8 linhas em vez de 60. Se nenhum marcador de falha for reconhecido, devolve a saída integral: esconder o motivo é pior que gastar contexto.

### Anti-laço

A consulta a `stop_hook_active` é a **primeira** coisa que o hook faz, e retorna em 0,02 s — o ciclo de reentrada não paga os segundos do gate. Sem ela, um bloqueio que o agente não consiga satisfazer vira laço infinito.

## Armadilha ao consumir ferramentas de `Tools/`

Os scripts de `Tools/` emitem os achados via `Write-Host` e `Out-Host`, que escrevem no **host** e não no pipeline. Capturar com `2>&1` no mesmo processo devolve string vazia e perde exatamente o detalhe que interessa (`UTF8_BOM_FORBIDDEN` vs. `POWERSHELL_BOM_MISSING`).

`Invoke-GovernedScript` (em `HookCommon.psm1`, usado por `Invoke-EncodingCheck` e `Invoke-GovernanceGate`) resolve executando como **processo filho**, onde tudo converge para o stdout. Os caminhos trafegam por arquivo temporário, nunca interpolados na linha de comando — nome com aspas ou espaço não vira injeção de argumento.

## Testar sem reiniciar a sessão

O harness entrega o payload por **stdin**; `CLAUDE_TOOL_INPUT` é apenas uma
conveniência de teste que `Get-HookPayload` aceita como primeira opção. Testar só
pela variável não prova que o hook funciona em produção — foi assim que três hooks
inertes passaram despercebidos. Prefira o teste por stdin, que é o caminho real:

```powershell
$payload = @{ tool_name = 'Write'; tool_input = @{ file_path = "C:\Automacoes\algum\arquivo.py" } } | ConvertTo-Json -Compress
$env:CLAUDE_PROJECT_DIR = "C:\Automacoes"
$payload | pwsh -NoProfile -File ".\.claude\hooks\Assert-FileEncoding.ps1"; "exit=$LASTEXITCODE"
```

Hooks **inline** no `settings.json` precisam ler stdin explicitamente
(`[Console]::In.ReadToEnd()`); só os scripts daqui herdam o fallback de
`Get-HookPayload`.
