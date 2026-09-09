#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
<#
.SYNOPSIS
    Contrato do hook .agents/hooks/PostToolUse-AutoFix.ps1 — carimbo de BOM.

.DESCRIPTION
    Este e' o unico hook do Antigravity que ESCREVE bytes em arquivos, e a
    logica de carimbo de BOM ganhou casos delicados que nao tinham trava:

    1. `.ps1`/`.psm1` sem BOM, corpo ja' UTF-8 valido  -> carimba BOM.
    2. Corpo com byte CP-1252 solto (nao decodifica como UTF-8) -> NAO carimba,
       avisa em stderr. Colar BOM na frente faria o arquivo se anunciar UTF-8
       com corpo que nao e' — mascara POWERSHELL_BOM_MISSING sem corrigir nada.
    3. Arquivo vazio -> nao vira arquivo de 3 bytes so' com BOM.
    4. UTF-16 LE/BE -> transcodifica para UTF-8 with BOM (sem corromper).
    5. Ja' tem BOM UTF-8 -> byte-identico, nao mexe.

    O payload vai por STDIN no formato toolCall, como o Antigravity entrega.
#>

BeforeAll {
    $script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $script:Hook = Join-Path $script:RepoRoot '.agents\hooks\PostToolUse-AutoFix.ps1'

    $script:HostPath = (Get-Command -Name 'pwsh' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1).Source
    if (-not $script:HostPath) {
        $script:HostPath = (Get-Command -Name 'powershell' -CommandType Application |
            Select-Object -First 1).Source
    }

    function Invoke-AutoFix {
        <#
            Roda o hook com { toolCall: { args: { TargetFile: <abs> } } } por
            stdin. Devolve o stderr capturado (para checar os avisos).
        #>
        param([Parameter(Mandatory)][string]$TargetFile)

        $payload = @{ toolCall = @{ args = @{ TargetFile = $TargetFile } } } |
            ConvertTo-Json -Compress
        $errFile = Join-Path $TestDrive ("stderr-{0}.txt" -f ([guid]::NewGuid().ToString('N')))
        $payload | & $script:HostPath -NoProfile -NonInteractive -File $script:Hook `
            1>$null 2>$errFile
        return (Get-Content -LiteralPath $errFile -Raw -ErrorAction SilentlyContinue)
    }

    function New-TempFile {
        param(
            [Parameter(Mandatory)][string]$Name,
            [Parameter(Mandatory)][AllowEmptyCollection()][byte[]]$Bytes
        )
        $path = Join-Path $TestDrive $Name
        [System.IO.File]::WriteAllBytes($path, $Bytes)
        return $path
    }
}

Describe "PostToolUse-AutoFix: carimbo de BOM em PowerShell" {

    It "carimba BOM UTF-8 em .ps1 sem BOM com corpo UTF-8 valido" {
        # 'Write-Output "acao"' com 'c'-cedilha (U+00E7) em UTF-8 = 0xC3 0xA7.
        $corpo = [System.Text.Encoding]::UTF8.GetBytes("Write-Output 'a" + [char]0x00E7 + "ao'")
        $path = New-TempFile -Name 'sem-bom.ps1' -Bytes $corpo

        Invoke-AutoFix -TargetFile $path | Out-Null

        $depois = [System.IO.File]::ReadAllBytes($path)
        $depois[0..2] | Should -Be @(0xEF, 0xBB, 0xBF)
        # Corpo preservado byte a byte apos o BOM.
        ($depois[3..($depois.Length - 1)] -join ',') | Should -Be ($corpo -join ',')
    }

    It "NAO carimba BOM quando o corpo tem byte CP-1252 solto (mascara corrupcao)" {
        # 0xE9 e' 'e'-agudo em CP-1252/Latin-1, mas como UTF-8 e' um lead byte
        # que exige 2 continuacoes; seguido de ASCII, e' invalido.
        $corpo = [byte[]]@(0x23, 0x20) + [byte[]]@(0xE9) + [System.Text.Encoding]::ASCII.GetBytes("cao")
        $path = New-TempFile -Name 'cp1252.ps1' -Bytes $corpo

        $err = Invoke-AutoFix -TargetFile $path

        $depois = [System.IO.File]::ReadAllBytes($path)
        ($depois -join ',') | Should -Be ($corpo -join ',')   # intacto
        $err | Should -Match 'BOM NAO foi adicionado'
    }

    It "nao transforma .ps1 vazio em arquivo de 3 bytes" {
        $path = New-TempFile -Name 'vazio.ps1' -Bytes ([byte[]]@())

        Invoke-AutoFix -TargetFile $path | Out-Null

        (Get-Item -LiteralPath $path).Length | Should -Be 0
    }

    It "transcodifica UTF-16 LE para UTF-8 with BOM sem corromper" {
        $texto = "Write-Output 'a" + [char]0x00E7 + "ao'"
        $bytes = [System.Text.Encoding]::Unicode.GetPreamble() +
                 [System.Text.Encoding]::Unicode.GetBytes($texto)
        $path = New-TempFile -Name 'utf16le.ps1' -Bytes $bytes

        Invoke-AutoFix -TargetFile $path | Out-Null

        $depois = [System.IO.File]::ReadAllBytes($path)
        $depois[0..2] | Should -Be @(0xEF, 0xBB, 0xBF)
        $utf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $utf8.GetString($depois[3..($depois.Length - 1)]) | Should -Be $texto
    }

    It "nao mexe em .ps1 que ja' tem BOM UTF-8 (byte-identico)" {
        $bytes = [byte[]]@(0xEF, 0xBB, 0xBF) +
                 [System.Text.Encoding]::UTF8.GetBytes("Write-Output 'ok'")
        $path = New-TempFile -Name 'com-bom.ps1' -Bytes $bytes

        Invoke-AutoFix -TargetFile $path | Out-Null

        ([System.IO.File]::ReadAllBytes($path) -join ',') | Should -Be ($bytes -join ',')
    }

    It "sempre emite {} no stdout e sai 0" {
        $path = New-TempFile -Name 'saida.ps1' -Bytes ([System.Text.Encoding]::UTF8.GetBytes("Write-Output 1"))
        $payload = @{ toolCall = @{ args = @{ TargetFile = $path } } } | ConvertTo-Json -Compress
        $out = $payload | & $script:HostPath -NoProfile -NonInteractive -File $script:Hook 2>$null
        $LASTEXITCODE | Should -Be 0
        $out.Trim() | Should -Be '{}'
    }
}
