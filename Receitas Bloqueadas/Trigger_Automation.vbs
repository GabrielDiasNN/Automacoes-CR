Option Explicit

' =============================================================================
' Trigger_Automation.vbs (UNIVERSAL TEMPLATE v3.0)
' Descricao: Disparador mestre para projetos automacao.
' Modulo: RECEITAS BLOQUEADAS
' =============================================================================

Dim excelApp, wb, fso, wsh
Dim scriptStart, logPath, execId

' ========== CONFIGURACOES DO MODULO ==========
Dim excelPath, macroName
excelPath = "C:\Automacoes\Receitas Bloqueadas\Receitas Bloqueadas.xlsm"
macroName = "ExecutarProcessoCompleto"
logPath   = "C:\Automacoes\Receitas Bloqueadas\Logs\Execution.log"

' [FEATURE FLAG] Monitoramento de Timeout via Log VBA (Estilo "Robo Fiscal")
Dim USE_TIMEOUT_MONITOR, vbaLogPath, maxTimeoutSeconds
USE_TIMEOUT_MONITOR = True
vbaLogPath          = "C:\Automacoes\Receitas Bloqueadas\Logs\VBA_Internal.log"
maxTimeoutSeconds   = 300

' [FEATURE FLAG] Script Pos-Execucao (Ex: WhatsApp Node.js Bridge)
Dim POST_EXECUTION_BAT
POST_EXECUTION_BAT  = "C:\Automacoes\Receitas Bloqueadas\RunWhatsApp.bat"
' =============================================

scriptStart = Timer
Set fso = CreateObject("Scripting.FileSystemObject")

' ---------- FUNCOES UTILITARIAS ----------
Function AgoraBR()
    Dim d: d = Now
    AgoraBR = Right("0" & Day(d), 2) & "/" & Right("0" & Month(d), 2) & "/" & Year(d) & " " & _
              Right("0" & Hour(d), 2) & ":" & Right("0" & Minute(d), 2) & ":" & Right("0" & Second(d), 2)
End Function

Function SecondsSince(ByVal startTimer)
    Dim diff: diff = Timer - startTimer
    If diff < 0 Then diff = diff + 86400
    SecondsSince = diff
End Function

Function ElapsedSeconds()
    Dim diff: diff = SecondsSince(scriptStart)
    ElapsedSeconds = Replace(FormatNumber(diff, 2, -1, 0, 0), ",", ".")
End Function

Sub EnsureLogFolder(caminhoAbsoluto)
    Dim parentFolder
    On Error Resume Next
    parentFolder = fso.GetParentFolderName(caminhoAbsoluto)
    If parentFolder <> "" Then
        If Not fso.FolderExists(parentFolder) Then fso.CreateFolder parentFolder
    End If
    Err.Clear
End Sub

Sub WriteLog(level, msg)
    Dim txtStream
    On Error Resume Next
    EnsureLogFolder logPath
    Set txtStream = fso.OpenTextFile(logPath, 8, True)
    If Err.Number = 0 Then
        txtStream.WriteLine "[" & AgoraBR() & "] [VBS] [" & level & "] " & msg
        txtStream.Close
    End If
    Err.Clear
End Sub

Function GerarExecId()
    Dim d: d = Now
    GerarExecId = Year(d) & Right("0" & Month(d), 2) & Right("0" & Day(d), 2) & "_" & _
                  Right("0" & Hour(d), 2) & Right("0" & Minute(d), 2) & Right("0" & Second(d), 2)
End Function

Sub LimparObjetosExcel()
    On Error Resume Next
    If Not wb Is Nothing Then
        wb.Close False
        Set wb = Nothing
    End If
    If Not excelApp Is Nothing Then
        excelApp.DisplayAlerts = False
        excelApp.ScreenUpdating = False
        excelApp.EnableEvents = False
        excelApp.Quit
        Set excelApp = Nothing
    End If
    Err.Clear
End Sub

Sub EncerrarComErro(exitCode, msg)
    WriteLog "ERRO", msg & " | elapsedSec=" & ElapsedSeconds()
    Call LimparObjetosExcel()
    WriteLog "INFO", "FIM - VBScript com erro. ExitCode=" & exitCode & " | elapsedSec=" & ElapsedSeconds()
    WriteLog "INFO", "========================================================="
    WScript.Quit exitCode
End Sub

' ---------- MONITORES AVANCADOS ----------
Function ExtrairVersao(texto)
    On Error Resume Next
    Dim re, m
    Set re = CreateObject("VBScript.RegExp")
    re.Pattern = "Vers[aã]o:\s*([^\r\n\|]+)"
    re.IgnoreCase = True
    re.Global = False
    If re.Test(texto) Then
        Set m = re.Execute(texto)
        ExtrairVersao = Trim(m(0).SubMatches(0))
    Else
        ExtrairVersao = ""
    End If
    On Error GoTo 0
End Function

' =============================================================================
' INICIO DA EXECUCAO
' =============================================================================
If WScript.Arguments.Count > 0 Then
    execId = WScript.Arguments(0)
Else
    execId = "MANUAL_" & GerarExecId()
End If

WriteLog "INFO", "========================================================="
WriteLog "INFO", "INICIO - Execucao via VBScript (Receitas Bloqueadas) [ExecId=" & execId & "]"
WriteLog "INFO", "Workbook=" & excelPath

If Not fso.FileExists(excelPath) Then Call EncerrarComErro(1, "Arquivo Excel nao encontrado: " & excelPath)

Dim roboVersao, tamanhoInicialLogVBA
roboVersao = "(desconhecida)"
tamanhoInicialLogVBA = 0

If USE_TIMEOUT_MONITOR Then
    EnsureLogFolder vbaLogPath
    On Error Resume Next
    If Not fso.FileExists(vbaLogPath) Then
        Dim tempObj: Set tempObj = fso.CreateTextFile(vbaLogPath, True): tempObj.Close
    End If
    tamanhoInicialLogVBA = fso.GetFile(vbaLogPath).Size
    Err.Clear
    On Error GoTo 0
    WriteLog "INFO", "Monitoramento de Timeout Ativado. LogVBAInicial=" & tamanhoInicialLogVBA & " bytes"
End If

On Error Resume Next
Set excelApp = CreateObject("Excel.Application")
If Err.Number <> 0 Or (excelApp Is Nothing) Then Call EncerrarComErro(2, "Falha ao iniciar Excel. Err=" & Err.Number)

excelApp.Visible = False
excelApp.DisplayAlerts = False
excelApp.ScreenUpdating = False
excelApp.EnableEvents = False
excelApp.AskToUpdateLinks = False

Set wb = excelApp.Workbooks.Open(excelPath)
If Err.Number <> 0 Or (wb Is Nothing) Then Call EncerrarComErro(3, "Falha ao abrir workbook. Err=" & Err.Number)
If wb.ReadOnly Then Call EncerrarComErro(7, "Workbook aberto em modo somente leitura. Possivel bloqueio por outra instancia: " & excelPath)

WriteLog "INFO", "Executando macro: " & macroName
Err.Clear
excelApp.Run macroName, execId

If Err.Number <> 0 Then
    Call EncerrarComErro(4, "Falha na execucao da macro. Err=" & Err.Number)
End If
On Error GoTo 0

' ---------------------------------------------------------------------------
' BLOCO: MONITORAMENTO DE TIMEOUT (OPCIONAL)
' ---------------------------------------------------------------------------
Dim encontrouFim, sucessoVBA
encontrouFim = True
sucessoVBA = True

If USE_TIMEOUT_MONITOR Then
    encontrouFim = False
    sucessoVBA = False
    WriteLog "INFO", "Aguardando conclusao via leitura de Log (Max Timeout: " & maxTimeoutSeconds & "s)..."

    Dim tempoRegInicio, ultimaChecagem, tamanhoAnterior, tamanhoAtual
    Dim streamArq, conteudoNovo, ver

    tempoRegInicio = Timer
    ultimaChecagem = Timer
    tamanhoAnterior = tamanhoInicialLogVBA

    Do While Not encontrouFim And SecondsSince(tempoRegInicio) < maxTimeoutSeconds
        On Error Resume Next
        tamanhoAtual = fso.GetFile(vbaLogPath).Size

        If tamanhoAtual > tamanhoAnterior Then
            ultimaChecagem = Timer
            Set streamArq = fso.OpenTextFile(vbaLogPath, 1)
            Dim conteudoCompleto: conteudoCompleto = streamArq.ReadAll
            streamArq.Close

            If Len(conteudoCompleto) > tamanhoInicialLogVBA Then
                conteudoNovo = Mid(conteudoCompleto, tamanhoInicialLogVBA + 1)
                ver = ExtrairVersao(conteudoNovo)
                If ver <> "" And ver <> roboVersao Then roboVersao = ver

                If InStr(conteudoNovo, "FIM DO PROCESSO.") > 0 Then
                    encontrouFim = True
                    sucessoVBA = (InStr(conteudoNovo, "Resultado=Sucesso") > 0)
                    Exit Do
                ElseIf InStr(conteudoNovo, "ERRO FATAL") > 0 Then
                    encontrouFim = True
                    sucessoVBA = False
                    Exit Do
                End If
            End If
            tamanhoAnterior = tamanhoAtual
        End If
        Err.Clear
        On Error Goto 0
        WScript.Sleep 3000
    Loop

    If Not encontrouFim Then Call EncerrarComErro(5, "TIMEOUT: VBA nao registrou termino em " & maxTimeoutSeconds & "s")
    If Not sucessoVBA Then Call EncerrarComErro(6, "VBA reportou falha/erro fatal nos logs")
    WriteLog "INFO", "VBA reportou sucesso (v" & roboVersao & ")"
Else
    WriteLog "INFO", "Macro executada (Monitoramento offline)."
End If

' ---------------------------------------------------------------------------
' FECHAMENTO SEGURO
' ---------------------------------------------------------------------------
Err.Clear
On Error Resume Next
If USE_TIMEOUT_MONITOR And sucessoVBA Then wb.Save
wb.Close False
excelApp.Quit
Set wb = Nothing
Set excelApp = Nothing
Err.Clear
On Error Goto 0

' ---------------------------------------------------------------------------
' BLOCO: SCRIPT POS-EXECUCAO (OPCIONAL)
' ---------------------------------------------------------------------------
If POST_EXECUTION_BAT <> "" Then
    If fso.FileExists(POST_EXECUTION_BAT) Then
        Dim wshTemp, cmdExe, comandoBat, batExitCode
        Set wshTemp = CreateObject("WScript.Shell")
        cmdExe = wshTemp.ExpandEnvironmentStrings("%ComSpec%")
        If cmdExe = "" Or cmdExe = "%ComSpec%" Then cmdExe = "cmd.exe"

        comandoBat = """" & cmdExe & """ /c """"" & POST_EXECUTION_BAT & """ """ & execId & """ AUTO"""

        WriteLog "INFO", "Disparando BAT pos-execucao. ExecId=" & execId & " | Comando=" & comandoBat

        wshTemp.CurrentDirectory = fso.GetParentFolderName(POST_EXECUTION_BAT)
        batExitCode = wshTemp.Run(comandoBat, 0, True)

        If batExitCode = 40 Then
            WriteLog "INFO", "Script pos-execucao ignorado por lock ativo (ExitCode 40)."
        ElseIf batExitCode = 23 Then
            WriteLog "INFO", "Script pos-execucao adiado por cooldown de retry no bridge WhatsApp (ExitCode 23)."
        ElseIf batExitCode <> 0 Then
            WriteLog "WARN", "Script pos-execucao retornou ExitCode " & batExitCode
        End If
        WriteLog "INFO", "Pos-execucao concluida."
        Set wshTemp = Nothing
    Else
        WriteLog "WARN", "Script pos-execucao nao encontrado: " & POST_EXECUTION_BAT
    End If
End If

WriteLog "INFO", "FIM - VBScript com sucesso. elapsedSec=" & ElapsedSeconds()
WriteLog "INFO", "========================================================="
WScript.Quit 0
