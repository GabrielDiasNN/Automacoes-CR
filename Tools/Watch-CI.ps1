<#
.SYNOPSIS
    Monitora o GitHub Actions do repositório em tempo real.
.DESCRIPTION
    Requer acesso irrestrito a api.github.com (fora da rede corporativa ou via VPN).
    Autentica via GH_TOKEN ou gh auth login.
.EXAMPLE
    .\Tools\Watch-CI.ps1
    .\Tools\Watch-CI.ps1 -RunId 12345678
    .\Tools\Watch-CI.ps1 -Branch main -Follow
#>
[CmdletBinding()]
param(
    [string]$RunId,
    [string]$Branch = 'main',
    [switch]$Follow,
    [string]$Repo = 'GabrielDiasNN/automacoes'
)

$ErrorActionPreference = 'Stop'

function Invoke-GitHubAPI {
    param([string]$Path)
    $token = if ($env:GH_TOKEN) { $env:GH_TOKEN } else { (gh auth token 2>$null) }
    if (-not $token) { throw "Configure GH_TOKEN ou execute: gh auth login" }
    $headers = @{
        Authorization = "Bearer $token"
        Accept        = 'application/vnd.github+json'
        'User-Agent'  = 'Watch-CI'
    }
    $uri = "https://api.github.com$Path"
    try {
        (Invoke-RestMethod -Uri $uri -Headers $headers -TimeoutSec 15).PSObject.Copy()
    } catch [System.Net.WebException] {
        throw "API GitHub falhou (WebException) ($uri): $_"
    } catch [System.Exception] {
        throw "API GitHub falhou ($uri): $_"
    }
}

function Get-StatusIcon {
    param([string]$Status, [string]$Conclusion)
    if ($Status -eq 'completed') {
        switch ($Conclusion) {
            'success'   { return '[OK]' }
            'failure'   { return '[FAIL]' }
            'cancelled' { return '[SKIP]' }
            default     { return "[?$Conclusion]" }
        }
    }
    if ($Status -eq 'in_progress') { return '[>>]' }
    return '[..]'
}

function Show-Run {
    param($Run)
    $icon = Get-StatusIcon -Status $Run.status -Conclusion $Run.conclusion
    $elapsed = if ($Run.updated_at) {
        $start = [datetime]$Run.created_at
        $end   = if ($Run.status -eq 'completed') { [datetime]$Run.updated_at } else { [datetime]::UtcNow }
        [int]($end - $start).TotalSeconds
    } else { 0 }

    Write-Host "`n$icon Run #$($Run.run_number) — $($Run.name)" -ForegroundColor Cyan
    Write-Host "   Commit : $($Run.head_sha.Substring(0,8)) — $($Run.head_commit.message -replace "`n.*", '')"
    Write-Host "   Status : $($Run.status) / $($Run.conclusion)"
    Write-Host "   Iniciou: $($Run.created_at) (+${elapsed}s)"
    Write-Host "   URL    : $($Run.html_url)"
}

function Show-Jobs {
    param([string]$RunId)
    $jobs = Invoke-GitHubAPI -Path "/repos/$Repo/actions/runs/$RunId/jobs"
    Write-Host "`n  Jobs:" -ForegroundColor Yellow
    foreach ($job in $jobs.jobs) {
        $icon = Get-StatusIcon -Status $job.status -Conclusion $job.conclusion
        $dur  = if ($job.completed_at -and $job.started_at) {
            [int]([datetime]$job.completed_at - [datetime]$job.started_at).TotalSeconds
        } else { $null }
        $durStr = if ($null -ne $dur) { " (${dur}s)" } else { '' }
        $color  = if ($job.conclusion -eq 'failure') { 'Red' } `
                  elseif ($job.conclusion -eq 'success') { 'Green' } `
                  else { 'Gray' }
        Write-Host "    $icon $($job.name)$durStr" -ForegroundColor $color

        if ($job.conclusion -eq 'failure') {
            $failedSteps = $job.steps | Where-Object { $_.conclusion -eq 'failure' }
            foreach ($s in $failedSteps) {
                Write-Host "        >> Step com falha: $($s.name)" -ForegroundColor Red
            }
        }
    }
}

# --- Main ---

if ($RunId) {
    $run = Invoke-GitHubAPI -Path "/repos/$Repo/actions/runs/$RunId"
    Show-Run -Run $run
    Show-Jobs -RunId $run.id

    if ($Follow -and $run.status -ne 'completed') {
        Write-Host "`nAguardando conclusao (Ctrl+C para sair)..." -ForegroundColor DarkGray
        do {
            Start-Sleep -Seconds 15
            $run = Invoke-GitHubAPI -Path "/repos/$Repo/actions/runs/$RunId"
            Write-Host "$(Get-Date -Format 'HH:mm:ss') — status: $($run.status)" -ForegroundColor DarkGray
        } while ($run.status -ne 'completed')

        Show-Run -Run $run
        Show-Jobs -RunId $run.id
    }
} else {
    # Lista runs recentes do branch
    $runs = Invoke-GitHubAPI -Path "/repos/$Repo/actions/runs?branch=$Branch&per_page=5"
    Write-Host "`nUltimas runs em '$Branch':" -ForegroundColor Cyan
    foreach ($run in $runs.workflow_runs) {
        $icon = Get-StatusIcon -Status $run.status -Conclusion $run.conclusion
        Write-Host ("  $icon [{0,8}] {1,-40} {2}" -f $run.id, $run.name, $run.created_at.Substring(0,16))
    }

    if ($runs.workflow_runs.Count -gt 0) {
        $latest = $runs.workflow_runs[0]
        Write-Host "`nDetalhando run mais recente (#$($latest.run_number))..." -ForegroundColor DarkGray
        Show-Run -Run $latest
        Show-Jobs -RunId $latest.id

        if ($Follow -and $latest.status -ne 'completed') {
            Write-Host "`nAguardando conclusao (Ctrl+C para sair)..." -ForegroundColor DarkGray
            do {
                Start-Sleep -Seconds 15
                $latest = Invoke-GitHubAPI -Path "/repos/$Repo/actions/runs/$($latest.id)"
                Write-Host "$(Get-Date -Format 'HH:mm:ss') — status: $($latest.status)" -ForegroundColor DarkGray
            } while ($latest.status -ne 'completed')

            Show-Run -Run $latest
            Show-Jobs -RunId $latest.id
        }
    }

    Write-Host ""
    Write-Host "Dica: use -Follow para aguardar em tempo real" -ForegroundColor DarkGray
    Write-Host "      use -RunId <id> para ver uma run especifica" -ForegroundColor DarkGray
    Write-Host "      use GH_TOKEN=<token> se nao autenticado no gh CLI" -ForegroundColor DarkGray
}
