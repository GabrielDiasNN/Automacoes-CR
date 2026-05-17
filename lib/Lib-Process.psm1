<#
.SYNOPSIS
    Módulo de Gerenciamento de Processos Assíncronos (Anti-Deadlock) v2.
.DESCRIPTION
    Este módulo injeta uma classe C# nativa para lidar com a execução de processos
    que geram grande volume de logs ou dados em stdout/stderr.
    
    Diferente da v1, esta versão NÃO utiliza callbacks (ScriptBlocks) para evitar
    instabilidade de threads no PowerShell 5.1. Em vez disso, expõe uma fila
    ConcurrentQueue que pode ser drenada pelo PowerShell.
.NOTES
    Version: 2.0.0
    ADR: 015 (Implementação de Wrapper C# para I/O Seguro - Thread-Safe Polling)
#>

$CsharpSource = @"
using System;
using System.Diagnostics;
using System.Text;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Threading;

namespace AutomationCore
{
    public class ProcessLogEntry
    {
        public string Message { get; set; }
        public string Level { get; set; }
    }

    public class NativeProcessRunner : IDisposable
    {
        private Process _process;
        public ConcurrentQueue<ProcessLogEntry> LogQueue { get; private set; }
        public StringBuilder StandardOutput { get; private set; }
        public StringBuilder StandardError { get; private set; }
        public bool IsFinished { get; private set; }
        public int ExitCode { get; private set; }
        public double DurationSeconds { get; private set; }
        private Stopwatch _watch;

        public NativeProcessRunner()
        {
            LogQueue = new ConcurrentQueue<ProcessLogEntry>();
            StandardOutput = new StringBuilder();
            StandardError = new StringBuilder();
            IsFinished = false;
        }

        public void Run(string fileName, string arguments, string workingDirectory = "", string inputData = null)
        {
            _watch = Stopwatch.StartNew();
            _process = new Process();
            _process.StartInfo.FileName = fileName;
            _process.StartInfo.Arguments = arguments;
            _process.StartInfo.WorkingDirectory = workingDirectory;
            _process.StartInfo.RedirectStandardOutput = true;
            _process.StartInfo.RedirectStandardError = true;
            _process.StartInfo.RedirectStandardInput = (inputData != null);
            _process.StartInfo.UseShellExecute = false;
            _process.StartInfo.CreateNoWindow = true;
            _process.StartInfo.StandardOutputEncoding = Encoding.UTF8;
            _process.StartInfo.StandardErrorEncoding = Encoding.UTF8;

            _process.OutputDataReceived += (sender, e) => {
                if (e.Data != null) {
                    lock(StandardOutput) StandardOutput.AppendLine(e.Data);
                    LogQueue.Enqueue(new ProcessLogEntry { Message = e.Data, Level = "INFO" });
                }
            };

            _process.ErrorDataReceived += (sender, e) => {
                if (e.Data != null) {
                    lock(StandardError) StandardError.AppendLine(e.Data);
                    LogQueue.Enqueue(new ProcessLogEntry { Message = e.Data, Level = "WARN" });
                }
            };

            _process.Start();
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();

            if (inputData != null)
            {
                _process.StandardInput.Write(inputData);
                _process.StandardInput.Close();
            }

            // Iniciamos uma thread para aguardar o fim sem travar o caller se necessário,
            // mas aqui o caller vai pollar IsFinished.
            ThreadPool.QueueUserWorkItem(_ => {
                _process.WaitForExit();
                // Pequeno delay para garantir que todos os eventos de log foram drenados do SO
                Thread.Sleep(500); 
                ExitCode = _process.ExitCode;
                _watch.Stop();
                DurationSeconds = Math.Round(_watch.Elapsed.TotalSeconds, 2);
                IsFinished = true;
            });
        }

        public void Dispose()
        {
            if (_process != null) {
                try { _process.Dispose(); } catch (System.Exception) {}
            }
        }
    }
}
"@

try {
    # Usamos um nome de classe único para evitar conflitos se a sessão já tiver a v1 carregada
    # Porém, como PS 5.1 não permite re-definir tipos, se houver conflito, o try/catch resolve.
    Add-Type -TypeDefinition $CsharpSource -Language CSharp
} catch [System.Exception] {
    # Se o erro for que o tipo já existe, ignoramos. Caso contrário, logamos.
    if ($_.Exception.Message -notlike "*já foi definido*" -and $_.Exception.Message -notlike "*already exists*") {
        Write-Warning "Falha ao carregar tipo AutomationCore via Add-Type: $($_.Exception.Message)"
    }
}

function Invoke-NativeProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$FilePath,
        [string]$Arguments = "",
        [string]$WorkingDirectory = $PSScriptRoot,
        [string]$InputData = $null,
        [scriptblock]$LogAction = $null
    )

    $runner = New-Object AutomationCore.NativeProcessRunner
    try {
        $runner.Run($FilePath, $Arguments, $WorkingDirectory, $InputData)

        while (-not $runner.IsFinished) {
            $entry = $null
            while ($runner.LogQueue.TryDequeue([ref]$entry)) {
                if ($null -ne $LogAction) {
                    $LogAction.Invoke($entry.Message, $entry.Level)
                }
            }
            Start-Sleep -Milliseconds 100
        }

        # Drenagem final após o processo terminar
        $entry = $null
        while ($runner.LogQueue.TryDequeue([ref]$entry)) {
            if ($null -ne $LogAction) {
                $LogAction.Invoke($entry.Message, $entry.Level)
            }
        }

        $result = New-Object PSObject -Property @{
            ExitCode = $runner.ExitCode
            StandardOutput = $runner.StandardOutput.ToString()
            StandardError = $runner.StandardError.ToString()
            DurationSeconds = $runner.DurationSeconds
        }

        return $result
    } finally {
        $runner.Dispose()
    }
}

Export-ModuleMember -Function Invoke-NativeProcess
