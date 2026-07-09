<#
.SYNOPSIS
    Registra o Orquestrador FastAPI como uma tarefa de inicializacao oculta.
.DESCRIPTION
    Para manter a Soberania e Resiliencia, este script cria uma Tarefa Agendada no Windows
    para iniciar o Start-Orchestrator.ps1 silenciosamente (em background) assim que o usuario logar.
#>
$ErrorActionPreference = "Stop"
$TaskName = "AutomationHub_Orchestrator_Service"
$ScriptPath = Join-Path $PSScriptRoot "Start-Orchestrator.ps1"

Write-Host "Criando Tarefa Agendada: $TaskName" -ForegroundColor Cyan

# Acao: Executar o powershell de forma oculta
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""

# Gatilho: Ao fazer logon com o usuario atual
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Configuracoes: Rodar indefinidamente, nao parar se na bateria, REINICIAR se falhar
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

# Principal: Roda com os privilegios do usuario atual (nao exige Admin)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
    Write-Host "[OK] Tarefa registrada com sucesso! O Orquestrador iniciara silenciosamente em cada login do usuario." -ForegroundColor Green
    Write-Host "Para iniciar agora manualmente de forma invisivel, execute:" -ForegroundColor Yellow
    Write-Host "Start-ScheduledTask -TaskName $TaskName" -ForegroundColor Yellow
} catch [System.Exception] {
    Write-Host "[ERRO] Falha ao registrar tarefa: $_" -ForegroundColor Red
}

