param(
    [string]$RootPath = $null,
    [string[]]$Paths = @(),

    # Pylint so' no diff: com -LintChangedOnly o pylint roda apenas sobre os .py de
    # -LintScopePaths (arquivos staged) e os arquivos que os importam; mypy e o veto a
    # 'pylint: disable=all' continuam sobre todo o alvo. Usado pelo pre-commit quando
    # um caminho critico promove a full_scan: o pylint completo custava ~231 s dos
    # ~317 s do gate Python (medido em 18/11/2026). O pylint completo segue
    # bloqueante no CI (job governanca-agregada, que nao passa este switch).
    [string[]]$LintScopePaths = @(),
    [switch]$LintChangedOnly
)

# A saida do git (ls-files) e' decodificada com [Console]::OutputEncoding. Herdando
# ibm850 do console, o nome "Producao" (com acento) chegava corrompido, o Test-Path
# falhava e os 33 .py de "Produção Beneficimento" eram descartados em silencio pelo
# mypy e pelo pylint, no hook e no CI (240 de 273 verificados ate 18/11/2026).
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) }
catch [System.IO.IOException] { Write-Verbose "Sem console para ajustar a codificacao: $($_.Exception.Message)" }

# ATENCAO: ao invocar este script para validar multiplos arquivos, use sempre o
# operador `&` in-process (ex.: `& $path -Paths $TargetPaths`), como faz
# Tools\ValidarAutomacoes.ps1. Invocacoes via `pwsh -File Test-PythonGovernance.ps1
# -Paths @(...)` a partir de OUTRO processo pwsh perdem elementos do array: o
# parser de CLI do pwsh.exe (modo -File) nao faz o binding rico de array do
# PowerShell e captura apenas o primeiro token, descartando os demais antes do
# script executar. O split abaixo recupera apenas o caso em que os caminhos
# chegam colapsados em uma unica string separada por virgula.
if ($Paths.Count -eq 1 -and $Paths[0] -match ',') {
    $Paths = $Paths[0] -split ',' | Where-Object { $_ }
}

if ([string]::IsNullOrEmpty($RootPath)) {
    $RootPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = 1
$env:PYLINTHOME = Join-Path $RootPath ".mypy_cache\pylint"
$env:MYPYPATH = "$(Join-Path $RootPath "Orchestrator");$RootPath;$(Join-Path $RootPath "lib\python")"
# Tools\oracle: os testes do Orchestrator importam as ferramentas (mcp_server etc.) pelo
# nome, como fazem em tempo de execução; sem isto o pylint reprova com E0401 o que o
# pytest resolve. Nenhum módulo de Tools\oracle colide com os das outras raízes.
$env:PYTHONPATH = "$($env:PYTHONPATH);$(Join-Path $RootPath "Orchestrator");$(Join-Path $RootPath "lib\python");$(Join-Path $RootPath "Produção Beneficimento\src");$(Join-Path $RootPath "Tools\oracle")"
New-Item -ItemType Directory -Force -Path $env:PYLINTHOME | Out-Null
Write-Host "=== Governanca Python (Type Hints & Pylint) ==="

$targetFiles = @()
if ($Paths.Count -gt 0) {
    $targetFiles = $Paths | Where-Object { $_ -match '\.py$' }
} else {
    $targetFiles = (git -c core.quotepath=false ls-files "*.py")
}

if ($targetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo Python (.py) para validar."
    exit 0
}

function Get-PythonTool {
    param([string]$ToolName)
    $venvTool = Join-Path $RootPath ".venv\Scripts\$ToolName.exe"
    if (Test-Path $venvTool) { return $venvTool }

    try {
        $commonDir = git -C $RootPath rev-parse --git-common-dir 2>$null
        if ($commonDir) {
            $mainRepo = if ([System.IO.Path]::IsPathRooted($commonDir)) {
                Split-Path $commonDir -Parent
            } else {
                Split-Path (Resolve-Path (Join-Path $RootPath $commonDir)).Path -Parent
            }
            $mainVenvTool = Join-Path $mainRepo ".venv\Scripts\$ToolName.exe"
            if (Test-Path $mainVenvTool) { return $mainVenvTool }
        }
    } catch [System.Exception] {
        # Mesma classe que Resolve-HubPythonExe em lib/Lib-Process.psm1: falha
        # de descoberta do repositorio principal nao pode sumir silenciosa. O
        # fluxo continua (Get-Command / $null abaixo) — so' passa a ter rastro.
        Write-Warning "Get-PythonTool ($ToolName): falha ao localizar o venv do repositorio principal via 'git rev-parse --git-common-dir': $($_.Exception.Message)"
    }

    if (Get-Command $ToolName -ErrorAction SilentlyContinue) { return $ToolName }
    return $null
}

$resolvedTargetFiles = @()
foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = Join-Path $RootPath $file
    if (-not (Test-Path -LiteralPath $fullPath)) {
        # Antes era um 'continue' mudo: foi assim que os .py com acento no caminho
        # sumiram do gate sem ninguem perceber.
        Write-Host "[AVISO] Arquivo listado mas nao encontrado, ignorado: $file" -ForegroundColor Yellow
        continue
    }
    Write-Host "Verificando: $file"
    $resolvedTargetFiles += $fullPath
}

if ($resolvedTargetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo Python (.py) existente para validar."
    exit 0
}

$hasErrors = $false

# Debito tecnico controlado: arquivos historicos com "pylint: disable=all" estao
# congelados no baseline. Arquivos novos nao podem nascer com a diretiva.
$baselinePath = Join-Path $PSScriptRoot "pylint-disable-all-baseline.txt"
$baseline = @()
if (Test-Path $baselinePath) {
    $baseline = Get-Content $baselinePath -Encoding UTF8 | Where-Object { $_ -and -not $_.StartsWith('#') }
}
foreach ($fullPath in $resolvedTargetFiles) {
    $normalizedRoot = ($RootPath -replace '/', '\').TrimEnd('\')
    $normalizedFull = $fullPath -replace '/', '\'
    $relative = $normalizedFull.Substring($normalizedRoot.Length).TrimStart('\') -replace '\\', '/'
    $head = Get-Content $fullPath -TotalCount 3 -ErrorAction SilentlyContinue
    if (($head -match 'pylint:\s*disable=all') -and ($baseline -notcontains $relative)) {
        Write-Host "[ERRO] '$relative' usa 'pylint: disable=all' e nao esta no baseline ($baselinePath). Arquivos novos devem passar no Pylint sem suprimir todos os checks." -ForegroundColor Red
        $hasErrors = $true
    }
}

$mypy = Get-PythonTool "mypy"
$pylint = Get-PythonTool "pylint"

# Arquivos do pylint. Sem -LintChangedOnly: todo o alvo (CI, modo direcionado).
# Com -LintChangedOnly: os .py alterados mais os dependentes diretos, isto e', os
# arquivos do alvo que importam um modulo alterado. Os dependentes cobrem o caso de
# um nome removido ou renomeado que quebra o importador (E0611/E1101), que o pylint
# so' acusa no arquivo que importa. A heuristica por nome de modulo inclui a mais
# (modulos homonimos de outras automacoes), nunca a menos para imports absolutos.
function Get-PylintScope {
    param([string[]]$AllFiles, [string[]]$ChangedRelative)

    $changedFull = @(
        $ChangedRelative |
            Where-Object { $_ -match '\.py$' } |
            ForEach-Object { Join-Path $RootPath ($_.Trim('"')) } |
            Where-Object { Test-Path -LiteralPath $_ }
    )
    if ($changedFull.Count -eq 0) { return @() }

    $stems = @(
        $changedFull | ForEach-Object {
            $leaf = [System.IO.Path]::GetFileNameWithoutExtension($_)
            if ($leaf -eq '__init__') { Split-Path -Leaf (Split-Path -Parent $_) } else { $leaf }
        } | Sort-Object -Unique
    )
    $alternation = ($stems | ForEach-Object { [regex]::Escape($_) }) -join '|'
    $importPattern = '(?m)^\s*(?:from\s+(?:[\w.]+\.)?(?:' + $alternation + ')(?:\.[\w.]+)?\s+import\b' +
        '|import\s+(?:[\w.]+\.)?(?:' + $alternation + ')\b' +
        '|from\s+[\w.]+\s+import\s+(?:\([^)]*?\b(?:' + $alternation + ')\b|[^\r\n#]*\b(?:' + $alternation + ')\b))'
    $importRegex = New-Object System.Text.RegularExpressions.Regex($importPattern)

    $changedSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($c in $changedFull) { [void]$changedSet.Add((Resolve-Path -LiteralPath $c).Path) }

    $scope = @($changedSet)
    foreach ($candidate in $AllFiles) {
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        if ($changedSet.Contains($resolved)) { continue }
        $text = [System.IO.File]::ReadAllText($resolved)
        if ($importRegex.IsMatch($text)) { $scope += $resolved }
    }
    return $scope
}

$pylintFiles = @($resolvedTargetFiles)
if ($LintChangedOnly) {
    $pylintFiles = @(Get-PylintScope -AllFiles $resolvedTargetFiles -ChangedRelative $LintScopePaths)
    Write-Host ("Pylint restrito ao diff: {0} arquivo(s) entre alterados e dependentes diretos (mypy segue sobre {1})." -f $pylintFiles.Count, $resolvedTargetFiles.Count) -ForegroundColor Gray
}

# Mypy roda agrupado por diretorio, nao um processo por arquivo: o overhead de
# startup dominava o gate (200s -> 45s no repositorio completo). O lote unico
# nao serve porque automacoes diferentes tem modulos homonimos
# (format_message.py, extract_oracle.py) e o mypy aborta com "Duplicate module";
# dentro de um mesmo diretorio essa colisao nao existe.
#
# Desde 18/11/2026 o mypy roda num job em segundo plano enquanto o pylint roda em
# primeiro plano: os dois sao independentes e o tempo de parede vira o do mais
# lento. Os grupos do mypy continuam em serie DENTRO do job porque compartilham o
# .mypy_cache, que nao e' seguro para escrita concorrente. O job herda as variaveis
# de ambiente acima (MYPYPATH etc.); o diretorio de trabalho e' passado explicito
# porque o PowerShell 5.1 inicia jobs em Documentos, e o cache fica no cwd.
$mypyJob = $null
$mypyGroups = @()
if ($mypy) {
    $mypyGroups = @(
        $resolvedTargetFiles | Group-Object { Split-Path -Parent $_ } |
            ForEach-Object { , [string[]]@($_.Group) }
    )
    $mypyJob = Start-Job -ScriptBlock {
        param([string]$MypyExe, [string]$WorkDir, [object[]]$Groups)
        Set-Location -LiteralPath $WorkDir
        $ErrorActionPreference = "Continue"
        foreach ($groupFiles in $Groups) {
            $files = @($groupFiles)
            $output = & $MypyExe --strict --explicit-package-bases --namespace-packages @files 2>&1 | ForEach-Object { "$_" }
            [pscustomobject]@{
                Name   = Split-Path -Parent $files[0]
                Exit   = $LASTEXITCODE
                Output = @($output)
            }
        }
    } -ArgumentList $mypy, (Get-Location).Path, $mypyGroups
} else {
    Write-Host "[AVISO] Mypy nao instalado. Validacao de tipagem Python pulada." -ForegroundColor Yellow
}

if (-not $pylint) {
    Write-Host "[AVISO] Pylint nao instalado. Validacao de qualidade Python pulada." -ForegroundColor Yellow
} elseif ($pylintFiles.Count -eq 0) {
    Write-Host "Pylint: nenhum .py alterado nem dependente no diff." -ForegroundColor Gray
} else {
    # C0411 (wrong-import-order) desabilitado: a deteccao de first-party do pylint
    # (baseada no PYTHONPATH/layout de pacotes) diverge da ordenacao real exigida
    # pelo isort (perfil "black", sem known-first-party configurado) que roda no
    # CI (job Lint Python). As duas ferramentas discordam sobre a mesma linha em
    # arquivos de Orchestrator/tests/ que importam de "app.*" e de bibliotecas
    # como fastapi/sqlalchemy/pytest — isort e o padrao real, pylint fica mudo.
    #
    # Agrupado por diretorio pelo MESMO motivo que o mypy acima: automacoes de
    # dominio tem modulos homonimos (models.py, queries.py, validators.py). Num
    # lote unico o pylint resolve `from models import ...` para o PRIMEIRO
    # models.py da lista e reprova o outro com E0611/E1101/W0632 — achados
    # falsos, apontando para linhas de um arquivo de outra automacao. Antes de
    # 26/08/2026 so `OBs Fluxo Sem Tingimento` tinha esse trio de nomes, entao a
    # colisao nao existia; a ORB-07 a tornou observavel.
    $pylintPorDiretorio = $pylintFiles | Group-Object { Split-Path -Parent $_ }

    foreach ($grupoPylint in $pylintPorDiretorio) {
        $arquivosGrupo = @($grupoPylint.Group)
        $pylintOutput = & $pylint --disable=C0114,C0115,C0116,R0801,C0413,C0301,C0302,C0411 @arquivosGrupo 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERRO] Falha de Qualidade de Codigo (Pylint) em $($grupoPylint.Name)" -ForegroundColor Red
            $pylintOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            $hasErrors = $true
        }
    }
}

if ($mypyJob) {
    $mypyResults = @(Receive-Job -Job $mypyJob -Wait -AutoRemoveJob)
    if ($mypyResults.Count -ne $mypyGroups.Count) {
        # Um job que morre no meio devolveria menos grupos; sem esta checagem o gate
        # passaria com tipagem nao verificada.
        Write-Host ("[ERRO] Job do Mypy devolveu {0} de {1} grupo(s)." -f $mypyResults.Count, $mypyGroups.Count) -ForegroundColor Red
        $hasErrors = $true
    }
    foreach ($result in $mypyResults) {
        if ($result.Exit -ne 0) {
            Write-Host "[ERRO] Falha de Tipagem Estrita (Mypy) em $($result.Name)" -ForegroundColor Red
            $result.Output | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            $hasErrors = $true
        }
    }
}

if ($hasErrors) {
    Write-Host "`n[FALHA] Foram encontrados erros de governanca Python. Corrija-os antes de commitar." -ForegroundColor Red
    exit 1
}

Write-Host "Validacao Python concluida com sucesso." -ForegroundColor Green
exit 0
