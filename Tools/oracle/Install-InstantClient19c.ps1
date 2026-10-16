<#
.SYNOPSIS
    Instala o Oracle Instant Client 19c Basic (64-bit) e replica a configuracao de rede tunada.

.DESCRIPTION
    Nao baixa nada. O ZIP do Instant Client precisa ser obtido pelo operador no site
    da Oracle (aceite de licenca) e informado em -ZipPath.

    Etapas:
      1. Valida o ZIP pelo SHA-256 (-ExpectedSha256, obrigatorio; so -SkipHashCheck
         dispensa, e de forma explicita).
      2. Extrai o Instant Client em -InstallDir, achatando a pasta raiz do ZIP.
         Pulada se oci.dll ja existir em -InstallDir (idempotente).
      3. Copia tnsnames.ora e sqlnet.ora de -SourceNetworkAdmin para
         <InstallDir>\network\admin.
      4. Faz backup do .env FORA do repositorio e atualiza ORACLE_CLIENT_LIB_DIR,
         ORACLE_CLIENT_PATH e TNS_ADMIN (demais linhas nao mudam).

    Com -DryRun mostra o plano e nao altera nada.

.EXAMPLE
    .\Tools\oracle\Install-InstantClient19c.ps1 -ZipPath "$env:USERPROFILE\Downloads\instantclient-basic-windows.x64-19.25.0.0.0dbru.zip" -InstallDir "$env:LOCALAPPDATA\Oracle\instantclient_19c" -SourceNetworkAdmin "$env:ORACLE_HOME\Network\Admin" -BackupDir "$env:LOCALAPPDATA\Oracle\backup-env" -DryRun

.EXAMPLE
    .\Tools\oracle\Install-InstantClient19c.ps1 -ZipPath "$env:USERPROFILE\Downloads\instantclient-basic-windows.x64-19.25.0.0.0dbru.zip" -InstallDir "$env:LOCALAPPDATA\Oracle\instantclient_19c" -SourceNetworkAdmin "$env:ORACLE_HOME\Network\Admin" -BackupDir "$env:LOCALAPPDATA\Oracle\backup-env" -ExpectedSha256 '<sha256-registrado>'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $ZipPath,

    # Sem padrao fixo: destino, origem do tnsnames.ora e backup dependem da maquina.
    [Parameter(Mandatory = $true)]
    [string] $InstallDir,

    [Parameter(Mandatory = $true)]
    [string] $SourceNetworkAdmin,

    [string] $EnvFile = (Join-Path $PSScriptRoot '..\..\.env'),

    [Parameter(Mandatory = $true)]
    [string] $BackupDir,

    [string] $ExpectedSha256 = '',

    [switch] $SkipHashCheck,

    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'

# Caminhos relativos são resolvidos pelo local do PowerShell, não pelo diretório do processo .NET.
$InstallDir = $PSCmdlet.GetUnresolvedProviderPathFromPSPath($InstallDir)
$SourceNetworkAdmin = $PSCmdlet.GetUnresolvedProviderPathFromPSPath($SourceNetworkAdmin)
$BackupDir = $PSCmdlet.GetUnresolvedProviderPathFromPSPath($BackupDir)

function Write-Step {
    param([string] $Message)
    Write-Host "[INSTALL-IC19] $Message"
}

# 1. ZIP e hash -----------------------------------------------------------------
$zip = (Resolve-Path -LiteralPath $ZipPath).Path
if ([System.IO.Path]::GetExtension($zip) -ne '.zip') {
    throw "Esperado um arquivo .zip do Instant Client: $zip"
}

$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
Write-Step "SHA-256 do ZIP: $hash"
# O oci.dll extraido e carregado pelo Python: sem hash conferido, nao instala.
# O DryRun so mostra o plano, entao nao exige o hash.
if (-not $ExpectedSha256 -and -not $SkipHashCheck -and -not $DryRun) {
    throw 'Informe -ExpectedSha256 com o valor publicado pela Oracle (ou -SkipHashCheck, assumindo o risco).'
}
if (-not $ExpectedSha256) {
    Write-Warning 'SHA-256 nao verificado (-SkipHashCheck).'
}
if ($ExpectedSha256 -and ($hash -ne $ExpectedSha256.Trim().ToUpperInvariant())) {
    throw 'SHA-256 do ZIP diverge do -ExpectedSha256. Abortando sem alterar nada.'
}

# 2. Pre-condicoes de rede e .env -----------------------------------------------
$tnsnamesSrc = Join-Path $SourceNetworkAdmin 'tnsnames.ora'
$sqlnetSrc = Join-Path $SourceNetworkAdmin 'sqlnet.ora'
if (-not (Test-Path -LiteralPath $tnsnamesSrc)) {
    throw "tnsnames.ora nao encontrado em $SourceNetworkAdmin"
}

$envPath = $PSCmdlet.GetUnresolvedProviderPathFromPSPath($EnvFile)
if (-not (Test-Path -LiteralPath $envPath)) {
    throw ".env nao encontrado em $envPath. Crie-o a partir de .env.example antes."
}

$ociDll = Join-Path $InstallDir 'oci.dll'
$needsExtract = -not (Test-Path -LiteralPath $ociDll)
$targetNetAdmin = Join-Path $InstallDir 'network\admin'

Write-Step 'Plano:'
if ($needsExtract) {
    Write-Step "  - extrair o ZIP em $InstallDir"
} else {
    Write-Step "  - extracao pulada: oci.dll ja existe em $InstallDir"
}
Write-Step "  - copiar tnsnames.ora (e sqlnet.ora, se existir) para $targetNetAdmin"
Write-Step "  - backup do .env em $BackupDir (fora do repositorio)"
Write-Step '  - atualizar no .env: ORACLE_CLIENT_LIB_DIR, ORACLE_CLIENT_PATH, TNS_ADMIN'

if ($DryRun) {
    Write-Step 'DryRun: nada foi alterado.'
    return
}

# 3. Extracao ---------------------------------------------------------------------
if ($needsExtract) {
    $staging = Join-Path ([System.IO.Path]::GetTempPath()) ('ic19-' + [guid]::NewGuid().ToString('N'))
    try {
        Expand-Archive -LiteralPath $zip -DestinationPath $staging -Force
        $ociInZip = Get-ChildItem -LiteralPath $staging -Filter 'oci.dll' -Recurse | Select-Object -First 1
        if (-not $ociInZip) {
            throw 'O ZIP nao contem oci.dll: nao e o Instant Client Basic Windows x64.'
        }
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        Copy-Item -Path (Join-Path $ociInZip.Directory.FullName '*') -Destination $InstallDir -Recurse -Force
    }
    finally {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
    }
    Write-Step "Instant Client extraido em $InstallDir"
}

if (-not (Test-Path -LiteralPath $ociDll)) {
    throw "oci.dll ausente apos a instalacao em $InstallDir."
}

# 4. Configuracao de rede ----------------------------------------------------------
New-Item -ItemType Directory -Force -Path $targetNetAdmin | Out-Null
Copy-Item -LiteralPath $tnsnamesSrc -Destination $targetNetAdmin -Force
if (Test-Path -LiteralPath $sqlnetSrc) {
    Copy-Item -LiteralPath $sqlnetSrc -Destination $targetNetAdmin -Force
    Write-Step "tnsnames.ora e sqlnet.ora copiados para $targetNetAdmin"
} else {
    Write-Step "AVISO: sqlnet.ora ausente em $SourceNetworkAdmin; so tnsnames.ora foi copiado."
}

# 5. .env: backup fora do repositorio e atualizacao das tres chaves -----------------
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $BackupDir ".env.$stamp.bak"
Copy-Item -LiteralPath $envPath -Destination $backup
# O .env tem credenciais: o backup fica legivel so pelo usuario atual (sem heranca).
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true, $false)
$usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($usuario, 'FullControl', 'Allow')))
Set-Acl -LiteralPath $backup -AclObject $acl
Write-Step "Backup do .env: $backup"

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$raw = [System.IO.File]::ReadAllText($envPath, $utf8NoBom)
$newline = if ($raw.Contains("`r`n")) { "`r`n" } else { "`n" }
$lines = New-Object System.Collections.Generic.List[string]
$lines.AddRange([string[]]($raw -split "\r?\n"))
if ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -eq '') {
    $lines.RemoveAt($lines.Count - 1)
}

$novasChaves = [ordered]@{
    ORACLE_CLIENT_LIB_DIR = $InstallDir
    ORACLE_CLIENT_PATH    = $InstallDir
    TNS_ADMIN             = $targetNetAdmin
}
foreach ($chave in $novasChaves.Keys) {
    $linha = "$chave=$($novasChaves[$chave])"
    $encontrou = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$chave\s*=") {
            $lines[$i] = $linha
            $encontrou = $true
        }
    }
    if (-not $encontrou) {
        $lines.Add($linha)
    }
}

[System.IO.File]::WriteAllText($envPath, (($lines -join $newline) + $newline), $utf8NoBom)
Write-Step 'Chaves atualizadas no .env: ORACLE_CLIENT_LIB_DIR, ORACLE_CLIENT_PATH, TNS_ADMIN.'

Write-Step 'Concluido. Instale tambem o Visual C++ Redistributable exigido pelo Instant Client, se a maquina nao tiver.'
Write-Step 'Validacao da instalacao: chamar a tool check_connection do servidor MCP (Tools/oracle/mcp_server.py).'
