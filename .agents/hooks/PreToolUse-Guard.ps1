#Requires -Version 5.1
<#
.SYNOPSIS
    Hook PreToolUse para o Antigravity: intercepta chamadas de ferramentas e bloqueia operacoes proibidas.

.DESCRIPTION
    Aplica as politicas centrais de governanca e seguranca do repositorio:
    1. Zero-Trust de Segredos e Dados: bloqueia gravacao/edicao em .env (exceto os
       arquivos-modelo .env.example/.env.template/.env.sample), bancos SQLite locais,
       arquivos de PID e certificados/chaves.
    2. Governanca Git: bloqueia comandos destrutivos (reset --hard, clean -fd, push --force).
    3. Cobertura de terminal: o mesmo Zero-Trust vale para `run_command`, tanto em
       redirecionamento de saida quanto em cmdlets/binarios de escrita e remocao.
       Sem isto o bloqueio de .env valeria so' para as ferramentas de edicao e
       seria contornavel com um `Set-Content .env`.

.INPUTS
    JSON via stdin contendo informacoes da chamada de ferramenta (toolCall).

.OUTPUTS
    JSON via stdout com formato { "decision": "allow"|"deny", "reason": "..." }
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# Padroes canonicos de alvos sensiveis do repositorio.
#
# `.env`: `(?![\w])` impede casar `.environment`/`.envrc`; a alternancia seguinte
# libera apenas os arquivos-modelo. Bloquear `.env*` e abrir excecao nominal e' o
# inverso do que se fazia antes (liberar todo sufixo), que deixava passar
# `.env.local` e `.env.production` — arquivos de segredo reais.
#
# Extensoes de credencial: o ponto e' escapado. Sem o escape, `.key` casava
# "qualquer caractere + key" e bloqueava fontes reais do Dashboard
# (useApiKey.ts, ApiKeyContext.tsx, ApiKeyGate.tsx).
$SensitiveTargetPattern = '(' +
    '\.env(?![\w])(?!\.(?:example|template|sample)(?![\w]))' +
    '|automacoes\.db|orchestrator\.db' +
    '|orchestrator\.pid|worker\.pid' +
    '|\.(?:pem|key|pfx|p12|crt|keystore)(?![\w])' +
    '|id_rsa' +
')'

# Padrao de comandos Git destrutivos
$DestructiveGitPattern = 'git\s+(reset\s+--hard|clean\s+.*(-[a-zA-Z]*f[a-zA-Z]*\b|--force\b)|push\s+.*(-[a-zA-Z]*f[a-zA-Z]*\b|--force\b|--force-with-lease\b)|checkout\s+(--\s+\.|\s*-f\b))'

# Verbos de escrita/remocao em terminal. Cobre PowerShell e os equivalentes
# POSIX disponiveis via Git Bash nesta maquina.
$WriteVerbPattern = '(' +
    'Set-Content|Add-Content|Out-File|Tee-Object|Clear-Content' +
    '|Remove-Item|Move-Item|Copy-Item|New-Item|Rename-Item' +
    '|\[System\.IO\.File\]::(?:Write|Append|Delete|Copy|Move)' +
    '|\brm\b|\bmv\b|\bcp\b|\bdd\b|\btee\b|\btruncate\b|\bdel\b|\berase\b' +
    '|\bsed\b[^|;]*-i' +
')'

function Read-StdinPayload {
    try {
        $raw = [Console]::In.ReadToEnd()
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return $null
        }
        return ($raw | ConvertFrom-Json)
    }
    catch [System.Exception] {
        # Payload ilegivel: sem como decidir com seguranca. O caminho de
        # chamada trata $null como "permitir" (fail-open deliberado, para nao
        # travar o agente), mas o motivo vai para stderr — falha silenciosa
        # aqui equivale a um guard desligado sem ninguem saber.
        [Console]::Error.WriteLine(
            "[WARN PreToolUse] Payload stdin ilegivel ({0}): decisao delegada ao runtime." -f $_.Exception.Message)
        return $null
    }
}

function Write-Decision {
    param(
        [string]$Decision,
        [string]$Reason = ""
    )

    $response = [ordered]@{
        decision = $Decision
    }
    if (-not [string]::IsNullOrWhiteSpace($Reason)) {
        $response["reason"] = $Reason
    }

    $json = $response | ConvertTo-Json -Compress
    [Console]::Out.WriteLine($json)
    exit 0
}

$payload = Read-StdinPayload

if ($null -eq $payload) {
    # Sem payload valido, permite execucao normal
    Write-Decision -Decision "allow"
}

$toolName = ""
$toolArgs = $null

if ($payload.PSObject.Properties.Name -contains "toolCall") {
    $toolName = [string]$payload.toolCall.name
    $toolArgs = $payload.toolCall.args
} elseif ($payload.PSObject.Properties.Name -contains "name") {
    $toolName = [string]$payload.name
    $toolArgs = $payload.args
}

$normalizedTool = $toolName.ToLowerInvariant().Replace("cortex_step_type_", "")

# 1. Checagem de ferramentas de edicao de arquivo
if ($normalizedTool -in @("write_to_file", "replace_file_content", "multi_replace_file_content", "writetofile", "replacefilecontent", "multireplacefilecontent")) {
    $targetFile = ""
    if ($null -ne $toolArgs) {
        if ($toolArgs.PSObject.Properties.Name -contains "TargetFile") {
            $targetFile = [string]$toolArgs.TargetFile
        } elseif ($toolArgs.PSObject.Properties.Name -contains "targetFile") {
            $targetFile = [string]$toolArgs.targetFile
        } elseif ($toolArgs.PSObject.Properties.Name -contains "target_file") {
            $targetFile = [string]$toolArgs.target_file
        } elseif ($toolArgs.PSObject.Properties.Name -contains "file_path") {
            $targetFile = [string]$toolArgs.file_path
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($targetFile)) {
        $normalizedPath = $targetFile.Replace('/', '\')
        if ($normalizedPath -match $SensitiveTargetPattern) {
            Write-Decision -Decision "deny" -Reason ("BLOQUEADO POR ZERO-TRUST: Alvo sensivel ou banco de dados protegido nao pode ser alterado pelo agente ({0})." -f [System.IO.Path]::GetFileName($targetFile))
        }
    }
}

# 2. Checagem de comandos de terminal (run_command)
if ($normalizedTool -in @("run_command", "runcommand")) {
    $commandLine = ""
    if ($null -ne $toolArgs) {
        if ($toolArgs.PSObject.Properties.Name -contains "CommandLine") {
            $commandLine = [string]$toolArgs.CommandLine
        } elseif ($toolArgs.PSObject.Properties.Name -contains "commandLine") {
            $commandLine = [string]$toolArgs.commandLine
        } elseif ($toolArgs.PSObject.Properties.Name -contains "command") {
            $commandLine = [string]$toolArgs.command
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($commandLine)) {
        if ($commandLine -match $DestructiveGitPattern) {
            Write-Decision -Decision "deny" -Reason "BLOQUEADO POR GOVERNANCA: Comando Git destrutivo (reset --hard, clean -fd, push --force) requer autorizacao explicita do usuario."
        }

        # Normaliza separadores para que 'Orchestrator/automacoes.db' e
        # 'Orchestrator\automacoes.db' sejam avaliados igualmente.
        $normalizedCommand = $commandLine.Replace('/', '\')

        # A checagem NAO pode avaliar a linha inteira de uma vez: verbo de
        # escrita e alvo sensivel podem estar em segmentos sem relacao
        # (`Get-Content .env; Set-Content saida.txt x`) ou o `.*` guloso do
        # redirecionamento pode atravessar um `;` (`echo ok > log.txt; cat
        # .env`). Divide em segmentos por ; && || | e quebra de linha, e
        # dentro de cada segmento trata `>`/`>>` como fronteira entre fonte
        # (leitura) e alvo (escrita) — mesma abordagem de
        # .claude\hooks\Assert-SensitiveWriteGuard.ps1.
        $redirectPattern = '(?<![0-9])>>?(?!\s*[&$])'
        $segments = $normalizedCommand -split '(\|\||&&|\||;|\r?\n)'

        foreach ($segment in $segments) {
            if ([string]::IsNullOrWhiteSpace($segment)) { continue }

            # O conteudo de -Value/-Body e dado, nao alvo: uma mencao ao nome
            # do arquivo dentro do valor escrito nao deve disparar bloqueio.
            $inspecionado = [regex]::Replace($segment, '-(Value|Body)\s+("[^"]*"|''[^'']*''|\S+)', '-$1 <omitido>')

            $parts = $inspecionado -split $redirectPattern
            $fonte = $parts[0]
            $alvos = @($parts | Select-Object -Skip 1)

            $bloqueia = $false

            # Alvo de redirecionamento sensivel bloqueia sozinho: o proprio
            # `>` e o verbo.
            foreach ($alvo in $alvos) {
                if ($alvo -match $SensitiveTargetPattern) { $bloqueia = $true }
            }

            # Na fonte, so bloqueia com verbo de escrita explicito no mesmo
            # segmento — senao qualquer leitura (`Get-Content .env`,
            # `grep CHAVE .env`) viraria bloqueio.
            if (-not $bloqueia -and ($fonte -match $SensitiveTargetPattern) -and ($fonte -match $WriteVerbPattern)) {
                $bloqueia = $true
            }

            if ($bloqueia) {
                Write-Decision -Decision "deny" -Reason "BLOQUEADO POR ZERO-TRUST: Escrita ou remocao de arquivo sensivel via terminal e proibida (.env, bancos locais, PIDs e chaves)."
            }
        }
    }
}

# Se passou em todas as verificacoes, permite a execucao
Write-Decision -Decision "allow"
