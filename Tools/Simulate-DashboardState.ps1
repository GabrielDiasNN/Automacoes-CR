$Tasks = @(
    @{
        name = "Automação Crítica - Fiscal"
        enabled = $true
        isRunning = $true
        runningSince = (Get-Date).AddSeconds(-45).ToString("o")
        avgDurationSec = 60
        scheduleText = "0/30 * * * *"
        lastResult = @{ exitCode = 0; finishedAt = (Get-Date).AddMinutes(-30).ToString("o") }
    },
    @{
        name = "Automação Lenta - Overtime"
        enabled = $true
        isRunning = $true
        runningSince = (Get-Date).AddSeconds(-120).ToString("o")
        avgDurationSec = 60
        scheduleText = "0 * * * *"
    },
    @{
        name = "Automação com Erro"
        enabled = $true
        isRunning = $false
        lastResult = @{ exitCode = 99; finishedAt = (Get-Date).AddMinutes(-5).ToString("o") }
        scheduleText = "Minutos: 0,30"
    },
    @{
        name = "Automação com Aviso (Exit 7)"
        enabled = $true
        isRunning = $false
        lastResult = @{ exitCode = 7; finishedAt = (Get-Date).AddMinutes(-15).ToString("o") }
        scheduleText = "Minutos: 15,45"
    }
)

for ($i = 1; $i -le 48; $i++) {
    $Tasks += @{
        name = "Tarefa Fake #$i"
        enabled = ($i % 5 -ne 0)
        isRunning = $false
        avgDurationSec = 15
        scheduleText = "0 0 * * *"
        lastResult = @{ exitCode = 0; finishedAt = (Get-Date).AddHours(-$i).ToString("o") }
    }
}

$SimulatedState = @{
    monitorVersion = "2.5.0-STRESS"
    startedAt = (Get-Date).AddDays(-1).ToString("o")
    generatedAt = (Get-Date).ToString("o")
    taskCount = $Tasks.Count
    runningTasks = 3
    windowMinutes = 15
    dashboardSchemaVersion = "1.2"
    
    health = @{
        lastHeartbeatAt = (Get-Date).ToString("o")
        lastConfigReloadAt = (Get-Date).AddMinutes(-30).ToString("o")
        lastConfigReloadStatus = "SUCCESS"
        mainLoopConsecutiveErr = 0
        checkIntervalSeconds = 20
    }
    
    metrics = @{
        cumulative = @{ TasksTriggered = 1500; TasksCompleted = 1450; TasksFinishedNonZero = 50 }
        window = @{ TasksTriggered = 45; TasksCompleted = 40; TasksFinishedNonZero = 5 }
    }
    
    alerts = @(
        @{ severity = "ERR"; message = "Falha crítica na conexão com Banco de Dados (Simulado)" }
        @{ severity = "WARN"; message = "Alta latência detectada no gateway de WhatsApp" }
    )
    
    tasks = $Tasks
    
    operations = @{
        apiMode = "HTTPS-REST"
        apiBaseUrl = "http://localhost:8765"
        endpoint = "/api/operations"
        statusMessage = "Monitor operando em modo simulação de testes"
    }
}

$JsonState = $SimulatedState | ConvertTo-Json -Depth 10 -Compress
$Template = Get-Content ".github/templates/dashboard-modern.html" -Raw
$FinalHtml = $Template.Replace("__DASHBOARD_JSON__", $JsonState).Replace("__REFRESH_SECONDS__", "30")

$FinalHtml | Out-File "Tools/Test-SimulatedDashboard.html" -Encoding utf8
Write-Host "Simulador gerado com sucesso em: Tools/Test-SimulatedDashboard.html"
Write-Host "Valores simulados: 52 tarefas, 2 alertas, 1 Overtime (Barra de Progresso pulsante)."
