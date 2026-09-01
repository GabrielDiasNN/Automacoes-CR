# Hooks locais do agente

Fiação em [`.claude/settings.json`](../settings.json). Hooks são carregados no início da sessão — **alterar estes arquivos exige reiniciar o Claude Code**.

| Arquivo | Evento | Matcher | Bloqueia? |
|---|---|---|---|
| `Assert-FileEncoding.ps1` | `PostToolUse` | `Edit\|Write` | Sim (exit 2) |
| `Assert-SensitiveWriteGuard.ps1` | `PreToolUse` | `Bash\|PowerShell` | Sim (exit 2) |
| `Register-GateRun.ps1` | `PostToolUse` | `Bash\|PowerShell` | Não (async) |
| `Assert-StopQualityGate.ps1` | `Stop` | `*` | Sim (exit 2) |
| `HookCommon.psm1` | — | — | módulo compartilhado |

## A fiação é parte do gate

O `settings.json` invoca estes scripts como `pwsh -Command "& '<script>'"`. Nessa
forma o `exit 2` do script **não** chega ao harness: quando o script escreve em
stderr, o processo termina com **1**, que o Claude Code trata como erro comum e
descarta. O gate emite a mensagem certa e não bloqueia nada.

| Invocação | Código visto pelo harness |
|---|---|
| `-Command "& '<script>'"` | `1` — gate inerte |
| `-Command "& '<script>'; exit $LASTEXITCODE"` | `2` — bloqueia |
| `-File <script>` | `2` — bloqueia |

`; exit $LASTEXITCODE` resolve o caminho feliz, mas **não** basta. Os scripts
começam com `$ErrorActionPreference = 'Stop'` seguido de `Import-Module
HookCommon.psm1`: se o módulo sumir, tiver erro de parse ou o `Set-StrictMode
-Version Latest` dele disparar, a exceção terminante encerra o `pwsh` **antes**
de alcançar o `exit`. Medido nessa condição: a forma com apenas o sufixo devolve
`1` (gate inerte) e, com `$LASTEXITCODE` nulo, `exit $LASTEXITCODE` devolve `0`
(aprova). Um único erro no módulo compartilhado deixaria os três gates inertes
de uma vez, sem sinal nenhum.

Por isso a forma canônica da fiação é **fail-closed**:

```powershell
$r = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $PWD.Path }
try { & "$r\.claude\hooks\<script>.ps1" }
catch { [Console]::Error.WriteLine("BLOQUEADO: <script>.ps1 falhou antes de decidir: $_"); exit 2 }
if ($null -eq $LASTEXITCODE) { exit 2 }
exit $LASTEXITCODE
```

Vale para **todo** comando que invoca um script daqui — inclusive
`Register-GateRun.ps1`, que hoje é `async` e sempre sai 0. Ali a forma não muda
nada em operação normal; existe para que o script não vire gate silenciosamente
inerte se algum dia passar a bloquear, e para que a fiação não tenha duas
convenções concorrentes.

Ao adicionar um hook novo, **teste o código de saída pela fiação real**, não só
rodando o script direto: os dois caminhos divergem. A cobertura automatizada
disso vive em [`lib/tests/Hooks-SensitiveWriteGuard.Tests.ps1`](../../lib/tests/Hooks-SensitiveWriteGuard.Tests.ps1),
que roda no job Pester do CI: além dos casos de bloqueio e de não-bloqueio
(payload por **stdin**, o caminho real), há um caso que executa o comando
literal extraído do `settings.json` e um que quebra `HookCommon.psm1` de
propósito para provar que a fiação falha fechada.

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

Dentro do segmento, `>` e `>>` são **fronteira entre fonte e alvo**: o que está à
esquerda é leitura, o que está à direita é o arquivo escrito. Por isso
`Get-Content .env > backup.txt` e `grep CHAVE .env > /tmp/out.txt` passam — antes
eram barrados, o que quebrava o fluxo documentado de ler a API Key assim que o
operador redirecionasse a saída. O alvo à direita bloqueia **sozinho**, sem
exigir verbo: `echo x > .env` continua barrado.

Erra para o lado conservador: na dúvida bloqueia, com a mensagem indicando o
segmento culpado. Dois casos conhecidos:

- **Texto que cita um comando** — uma mensagem de `git commit` ou um trecho de
  documentação que mencione o cmdlet e o arquivo na mesma linha é barrado, ainda
  que nada seja escrito. Descartar `-Value`/`-Body` cobre o cmdlet; texto livre
  não tem marcador que permita distingui-lo de um comando real.
- **Cópia/movimentação com o arquivo sensível como origem** — `Copy-Item .env
  .env.bak` é barrado. Distinguir origem de destino em `Copy-Item`/`Move-Item`
  exige parser posicional, e errar para o lado permissivo aqui liberaria
  `Copy-Item qualquer.txt .env`. O bloqueio também não é gratuito: copiar um
  arquivo de segredos é operação que vale passar pelo usuário.

Contorne reformulando o comando — não enfraqueça o padrão.

A detecção é **textual**: alvo montado dinamicamente ou alcançado por glob não é
reconhecido, e a lacuna não está fechada — `python -c "open('.env','w')"` passa
com exit 0. O guard reduz o alcance de um engano, não substitui permissão de
arquivo; não o trate como fronteira de segurança rígida.

A lista de alvos e o predicado vivem em `Test-SensitiveTarget`
(`HookCommon.psm1`), consumido tanto por este script quanto pelo guard inline de
`Edit|Write` no `settings.json` — não há mais duas implementações para manter em
sincronia. Antes havia: o inline usava `EndsWith('.env')` e o guard um regex, de
modo que a cobertura efetiva dependia de qual ferramenta o agente escolhia.

## Register-GateRun.ps1

Grava carimbo de tempo em `.claude/.state/` (ignorado pelo git) ao detectar `pytest`, `ValidarAutomacoes`/`Test-PythonGovernance`/`Test-SourceEncoding` ou `npm run build|lint` no comando executado.

O marcador registra que o comando **foi disparado**, não que passou. A leitura da saída continua sendo obrigação do agente.

## Assert-StopQualityGate.ps1

Barra o encerramento da tarefa quando o trabalho pendente não passou pela verificação correspondente:

- arquivos de `git status --porcelain` reprovando em `ValidarAutomacoes.ps1 -OnlyGovernance -NoCriticalPromotion -Paths` (os 15 checks: zero-trust, SQL, mypy/pylint, PSScriptAnalyzer, encoding, JSON, Playwright, manifesto, arquitetura, datas, semântica, Node, schema de evento de log);
- `.py` sob `Orchestrator/`, `lib/python/` ou `Produção Beneficimento/src/` alterado sem marcador de `pytest` posterior ao mtime da edição;
- `Dashboard/src/` alterado sem marcador de lint/build posterior.

Os dois últimos existem porque o gate de governança **não** roda pytest nem build do Dashboard.

### Por que `-Paths` não é opcional — e por que sozinho não bastava

| Modo | Custo |
|---|---|
| `-OnlyGovernance` sem alvos (`full_scan`) | **340 s** (medido 01/09/2026; eram 171 s quando o hook foi escrito) |
| `-OnlyGovernance -Paths <alterados>` | **~7 s**; 18 s com dois `.py` (mypy) |

Mesmos 15 checks. O timeout no `settings.json` é 240 s. A fonte final de verdade continua sendo o pre-commit hook e o CI.

**`-NoCriticalPromotion` é o que faz `-Paths` valer.** `Get-GovernanceTargetSummary.ps1` classifica como crítico qualquer alvo sob `lib\`, `Tools\`, `AGENTS.md`, `.github/workflows/` ou `.github/skills/` e, ao encontrar um, devolve `GovernancePaths = @()` — o gate então varre o repositório inteiro mesmo tendo recebido `-Paths`. Entre 27/08/2026 e 01/09/2026 isso fez o hook Stop estourar os 240 s em **13 de 13 execuções**: bastava um `lib/CLAUDE.md` no diff. A promoção continua ligada no pre-commit e no CI, onde o full_scan é a rede de segurança; no hook Stop, que precisa responder em segundos, ela é suprimida.

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
