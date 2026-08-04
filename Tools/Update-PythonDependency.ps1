<#
.SYNOPSIS
    Atualiza UMA dependencia Python nos lockfiles por substituicao cirurgica do bloco.

.DESCRIPTION
    Substitui o bloco de um pacote em requirements*.txt sem recompilar o lockfile,
    buscando os hashes sha256 reais na API publica do PyPI.

    POR QUE NAO USAR pip-compile: os lockfiles deste projeto sao uma UNIAO
    cross-platform mantida a mao - contem `uvloop` (marcador sys_platform != win32,
    so Linux) E `colorama` (exigido por click/uvicorn so no Windows). Nenhuma
    execucao de `pip-compile` produz os dois: a ferramenta resolve os marcadores de
    ambiente contra a plataforma onde roda e descarta silenciosamente o que nao se
    aplica. Recompilar no Windows perde `uvloop` e quebra o CI (Linux); recompilar
    no Linux perde `colorama` e quebra a instalacao no Windows - ambos comprovados
    empiricamente em 04/08/2026. O `pip-tools` nunca suportou lock universal, e
    `uv pip compile --universal` (que suportaria) nao conclui atras do proxy
    autenticado da rede corporativa.

    Historico: a recompilacao ja quebrou o CI duas vezes (03/08 e 04/08/2026).
    Ver issue #16 e CHANGELOG [1.3.23]-[1.3.24].

.PARAMETER Package
    Nome do pacote como aparece no lockfile (ex.: cryptography).

.PARAMETER Version
    Versao alvo (ex.: 50.0.0).

.PARAMETER RootPath
    Raiz do repositorio. Padrao: diretorio pai deste script.

.PARAMETER Files
    Lockfiles a atualizar. Padrao: os tres do projeto.

.PARAMETER WhatIf
    Mostra o que seria alterado sem escrever nada.

.EXAMPLE
    pwsh -File Tools\Update-PythonDependency.ps1 -Package cryptography -Version 50.0.0

.EXAMPLE
    pwsh -File Tools\Update-PythonDependency.ps1 -Package oracledb -Version 3.3.0 -WhatIf
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Package,

    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$RootPath = (Split-Path -Parent $PSScriptRoot),

    [string[]]$Files = @("requirements.txt", "requirements-test.txt", "requirements-dev.txt"),

    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
Write-Host "=== Atualizacao Cirurgica de Dependencia Python ==="
Write-Host "Pacote: $Package -> $Version"

# --- 1. Busca os hashes reais na API do PyPI -------------------------------
$uri = "https://pypi.org/pypi/$Package/$Version/json"
Write-Host "Consultando $uri ..."

# Rede corporativa: o proxy exige autenticacao integrada (responde 407 sem ela).
# O endereco e LIDO do sistema em tempo de execucao - nunca hardcode endereco nem
# credencial (o gate Zero-Trust reprova IP privado, e com razao).
$parametrosRede = @{}
try {
    $proxyUri = [System.Net.WebRequest]::GetSystemWebProxy().GetProxy($uri)
    if ($proxyUri -and $proxyUri.AbsoluteUri -ne $uri) {
        $parametrosRede["Proxy"] = $proxyUri.AbsoluteUri
        $parametrosRede["ProxyUseDefaultCredentials"] = $true
        Write-Host "Proxy do sistema detectado; usando credenciais integradas."
    }
} catch [System.Exception] {
    Write-Host "[AVISO] Nao foi possivel detectar o proxy do sistema: $($_.Exception.Message)"
}

try {
    $meta = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 60 @parametrosRede
} catch [System.Exception] {
    Write-Host "[ERRO] Falha ao consultar o PyPI: $($_.Exception.Message)"
    Write-Host "       Se for erro 407 (proxy), confirme que a sessao tem acesso a internet"
    Write-Host "       corporativa - o PyPI e alcancavel pelo pip nesta maquina."
    exit 1
}

$hashes = @($meta.urls | ForEach-Object { $_.digests.sha256 } | Sort-Object -Unique)
if ($hashes.Count -eq 0) {
    Write-Host "[ERRO] Nenhum artefato retornado para $Package==$Version."
    exit 1
}
Write-Host "Artefatos/hashes obtidos: $($hashes.Count)"

# --- 2. Substitui o bloco em cada lockfile ---------------------------------
# Bloco = linha "pacote==versao \" + linhas indentadas de --hash + comentarios "# via".
$escaped = [regex]::Escape($Package)
$blockRegex = [regex]::new(
    "^$escaped==[^\r\n]*(?:\r?\n[ \t]+(?:--hash|#)[^\r\n]*)*",
    [System.Text.RegularExpressions.RegexOptions]::Multiline
)

$alterados = 0
foreach ($file in $Files) {
    $path = Join-Path $RootPath $file
    if (-not (Test-Path $path)) {
        Write-Host "[AVISO] Nao encontrado, pulando: $file"
        continue
    }

    $content = [System.IO.File]::ReadAllText($path)
    $match = $blockRegex.Match($content)
    if (-not $match.Success) {
        Write-Host "[AVISO] $file nao contem o pacote $Package - pulando."
        continue
    }

    # Preserva o line ending do arquivo (requirements-test.txt e CRLF, os outros LF)
    $eol = if ($content.Contains("`r`n")) { "`r`n" } else { "`n" }

    # Preserva a anotacao de origem ("# via ...") exatamente como estava
    $viaLines = @(
        $match.Value -split "`r?`n" | Where-Object { $_.TrimStart().StartsWith("#") }
    )

    $novasLinhas = New-Object System.Collections.Generic.List[string]
    $novasLinhas.Add("$Package==$Version \")
    for ($i = 0; $i -lt $hashes.Count; $i++) {
        $sufixo = if ($i -lt $hashes.Count - 1) { " \" } else { "" }
        $novasLinhas.Add("    --hash=sha256:$($hashes[$i])$sufixo")
    }
    foreach ($via in $viaLines) { $novasLinhas.Add($via) }

    $versaoAntiga = ($match.Value -split "`r?`n")[0]
    $novoBloco = [string]::Join($eol, $novasLinhas)
    $novoConteudo = $content.Remove($match.Index, $match.Length).Insert($match.Index, $novoBloco)

    $rotuloEol = if ($eol -eq "`r`n") { "CRLF" } else { "LF" }
    if ($WhatIf) {
        Write-Host "[WHATIF] $file ($rotuloEol): $($versaoAntiga.TrimEnd(' \')) -> $Package==$Version"
    } else {
        # Sem BOM: requirements*.txt sao ASCII/UTF-8 puro (Test-SourceEncoding reprova BOM fora de .ps1)
        $utf8SemBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($path, $novoConteudo, $utf8SemBom)
        Write-Host "[OK] $file ($rotuloEol): $($versaoAntiga.TrimEnd(' \')) -> $Package==$Version"
    }
    $alterados++
}

if ($alterados -eq 0) {
    Write-Host "[ERRO] Nenhum lockfile continha $Package."
    exit 1
}

# --- 3. Instrucoes de validacao obrigatoria --------------------------------
# Os dois modos de falha desta classe passam despercebidos no diff superficial,
# e o pytest local passa mesmo com o lockfile corrompido.
Write-Host ""
Write-Host "=== VALIDACAO OBRIGATORIA ANTES DO COMMIT ==="
Write-Host "1) Apenas o pacote pretendido mudou:"
Write-Host "   git diff -U0 | Select-String '^[+-][a-zA-Z0-9_.-]+=='"
Write-Host "2) Instalacao no modo do CI (pega dependencia transitiva faltando):"
Write-Host "   .venv\Scripts\python -m pip install --require-hashes --dry-run -r requirements.txt -r requirements-test.txt -r requirements-dev.txt"
Write-Host "3) Suite completa:"
Write-Host "   cd Orchestrator; ..\.venv\Scripts\pytest"
Write-Host ""
Write-Host "NOTA: um ambiente que JA tem o pacote instalado mascara a falha do passo 2"
Write-Host "      (pip responde 'already satisfied' sem resolver). Em caso de duvida,"
Write-Host "      valide num venv limpo - foi assim que a quebra do CI passou despercebida."
exit 0
