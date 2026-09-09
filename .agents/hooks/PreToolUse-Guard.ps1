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

# Fonte unica de TODA a logica Zero-Trust: HookCommon.psm1 (.claude/hooks) — o
# padrao de alvos (Get-SensitiveTargetPattern, tambem usado pelo guard de
# Edit|Write do settings.json) e a deteccao de escrita sensivel em comando
# (Get-SensitiveWriteInCommand, tambem usada por Assert-SensitiveWriteGuard.ps1).
# Antes este script tinha copia propria de tudo isso e divergia: liberava
# .env.local/.env.production, nao cobria .pem/.key/id_rsa e casava verbos
# diferentes de escrita. Falha ao carregar o modulo bloqueia (fail-closed),
# como a fiacao inline de settings.json faz no mesmo cenario.
try {
    Import-Module (Join-Path $PSScriptRoot '..\..\.claude\hooks\HookCommon.psm1') -Force -DisableNameChecking
    $SensitiveTargetPattern = Get-SensitiveTargetPattern
}
catch [System.Exception] {
    [Console]::Error.WriteLine(
        "[WARN PreToolUse] Falha ao carregar padrao canonico de alvos sensiveis: {0}" -f $_.Exception.Message)
    [Console]::Out.WriteLine('{"decision":"deny","reason":"BLOQUEADO POR FALHA DE GOVERNANCA: nao foi possivel carregar o padrao de alvos sensiveis (HookCommon.psm1)."}')
    exit 0
}

# Padrao de comandos Git destrutivos.
#
# `\bgit(?:\.exe)?` mais um grupo opcional de opcoes globais (`-C <path>`,
# `-c k=v`, `--no-pager`...) antes do subcomando: sem isso `git -C . push
# --force` e `git.exe push --force` escapavam, pois o padrao exigia o
# subcomando colado no `git`. O grupo so' casa tokens que PARECEM opcao
# (`-x` / `--xxx` / com argumento) — nao texto livre — para nao bloquear
# `git commit -m "fala em reset --hard"`.
#
# A deteccao de flag de forca usa `(?<=\s)` para exigir que o `-` seja INICIO
# de um token de argumento, nao qualquer hifen dentro da string. Sem essa
# ancora, `.*(-[A-Za-z]*f[A-Za-z]*\b)` casava como substring livre em nomes de
# branch comuns: `git push origin feat/novo-fluxo` e `git push origin
# sync-from-main` eram bloqueados como se fossem `push --force`.
$DestructiveGitPattern = '\bgit(?:\.exe)?(?:\s+(?:-[cC]\s+\S+|--[A-Za-z][\w-]*=\S+|--[A-Za-z][\w-]*|-[A-Za-z]))*\s+(' +
    'reset\s+--hard\b' +
    '|clean\b[^;&|\r\n]*?(?<=\s)-(?:-force\b|[A-Za-z]*f[A-Za-z]*\b)' +
    '|push\b[^;&|\r\n]*?(?<=\s)-(?:-force(?:-with-lease)?\b|[A-Za-z]*f[A-Za-z]*\b)' +
    '|checkout\s+(?:--\s+\.|(?<=\s)-f\b)' +
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
        } else {
            # Ferramenta reconhecida, mas nenhuma das chaves de alvo
            # conhecidas apareceu em args: decide "allow" (fail-open, para
            # nao travar o agente por um schema inesperado), mas avisa —
            # senao o guard fica desligado para essa chamada sem ninguem
            # notar, ao contrario do fail-open de payload ilegivel acima.
            [Console]::Error.WriteLine(
                "[WARN PreToolUse] Ferramenta '{0}' reconhecida, mas nenhuma chave de alvo conhecida (TargetFile/targetFile/target_file/file_path) encontrada em args. Guard nao pode avaliar este alvo." -f $normalizedTool)
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
        } else {
            # Mesmo raciocinio do bloco de edicao de arquivo acima: fail-open
            # deliberado, mas avisado.
            [Console]::Error.WriteLine(
                "[WARN PreToolUse] Ferramenta '{0}' reconhecida, mas nenhuma chave de comando conhecida (CommandLine/commandLine/command) encontrada em args. Guard nao pode avaliar este comando." -f $normalizedTool)
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($commandLine)) {
        if ($commandLine -match $DestructiveGitPattern) {
            Write-Decision -Decision "deny" -Reason "BLOQUEADO POR GOVERNANCA: Comando Git destrutivo (reset --hard, clean -fd, push --force) requer autorizacao explicita do usuario."
        }

        # Segmentacao por ; && || |, fronteira `>`/`>>`, verbo de escrita E
        # alvo sensivel no mesmo segmento: tudo em Get-SensitiveWriteInCommand
        # (HookCommon.psm1), a MESMA rotina que .claude\hooks\
        # Assert-SensitiveWriteGuard.ps1 consome. O $SensitiveTargetPattern
        # ja veio do modulo (bloco de import no topo); o resto da logica
        # tambem, agora, em vez de reimplementado aqui.
        if (-not [string]::IsNullOrEmpty((Get-SensitiveWriteInCommand -CommandLine $commandLine))) {
            Write-Decision -Decision "deny" -Reason ("BLOQUEADO POR ZERO-TRUST: Escrita ou remocao de arquivo sensivel via terminal e proibida ({0})." -f (Get-SensitiveTargetDescription))
        }
    }
}

# Se passou em todas as verificacoes, permite a execucao
Write-Decision -Decision "allow"
