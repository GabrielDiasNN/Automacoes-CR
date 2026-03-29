Option Explicit

' =============================================================================
' Trigger_Automation.vbs (UNIVERSAL TEMPLATE v3.2)
' Descricao: Disparador mestre para projetos de automacao.
' Modulo: RECEITAS EMITIDAS
'
' Ajustes v3.2:
' - Configuracao centralizada em constantes
' - Monitoramento de timeout com suporte a virada de dia
' - IO de log com validacao imediata
' - Cleanup explicito de objetos Excel
' - Remocao de redundancias e variaveis ociosas
' =============================================================================

Dim excelApp
Dim wb
Dim fso
Dim scriptStart
Dim execId

Const EXCEL_PATH = "C:\Automacoes\Receitas Emitidas\Controle de Receitas Emitidas.xlsm"
Const MACRO_NAME = "AtualizarEEnviarOutlook"
Const LOG_PATH_MASTER = "C:\Automacoes\Receitas Emitidas\Logs\Execution.log"
Const LOG_PATH_VBA = "C:\Automacoes\Receitas Emitidas\Logs\VBA_Internal.log"

Const USE_TIMEOUT_MONITOR = True
Const MAX_TIMEOUT_SECONDS = 300
Const POLL_INTERVAL_MS = 3000

Const POST_EXECUTION_BAT = ""

scriptStart = Timer
Set fso = CreateObject("Scripting.FileSystemObject")

' ---------- FUNCOES UTILITARIAS ----------
Function AgoraBR()
    Dim dtmAgora
    dtmAgora = Now

    AgoraBR = Right("0" & Day(dtmAgora), 2) & "/" & _
              Right("0" & Month(dtmAgora), 2) & "/" & _
              Year(dtmAgora) & " " & _
              Right("0" & Hour(dtmAgora), 2) & ":" & _
              Right("0" & Minute(dtmAgora), 2) & ":" & _
              Right("0" & Second(dtmAgora), 2)
End Function

Function SecondsSince(ByVal startTimer)
    Dim dblDiff
    dblDiff = Timer - startTimer

    If dblDiff < 0 Then
        dblDiff = dblDiff + 86400
    End If

    SecondsSince = dblDiff
End Function

Function ElapsedSeconds()
    ElapsedSeconds = Replace(FormatNumber(SecondsSince(scriptStart), 2, -1, 0, 0), ",", ".")
End Function

Function GerarExecId()
    Dim dtmAgora
    dtmAgora = Now

    GerarExecId = Year(dtmAgora) & _
                  Right("0" & Month(dtmAgora), 2) & _
                  Right("0" & Day(dtmAgora), 2) & "_" & _
                  Right("0" & Hour(dtmAgora), 2) & _
                  Right("0" & Minute(dtmAgora), 2) & _
                  Right("0" & Second(dtmAgora), 2)
End Function

Function EnsureParentFolder(ByVal absolutePath)
    On Error Resume Next

    Dim parentFolder
    parentFolder = fso.GetParentFolderName(absolutePath)

    If Len(parentFolder) > 0 Then
        If Not fso.FolderExists(parentFolder) Then
            fso.CreateFolder parentFolder
        End If
    End If

    EnsureParentFolder = (Err.Number = 0)

    Err.Clear
    On Error GoTo 0
End Function

Function EnsureLogFile(ByVal filePath)
    On Error Resume Next

    Dim txtStream
    EnsureLogFile = False

    If Not EnsureParentFolder(filePath) Then
        Exit Function
    End If

    If Not fso.FileExists(filePath) Then
        Set txtStream = fso.CreateTextFile(filePath, True)
        If Err.Number <> 0 Then
            Err.Clear
            On Error GoTo 0
            Exit Function
        End If

        txtStream.Close
        Set txtStream = Nothing
    End If

    EnsureLogFile = True

    Err.Clear
    On Error GoTo 0
End Function

Sub WriteLog(ByVal logLevel, ByVal messageText)
    On Error Resume Next

    Dim txtStream

    If EnsureLogFile(LOG_PATH_MASTER) Then
        Set txtStream = fso.OpenTextFile(LOG_PATH_MASTER, 8, True)

        If Err.Number = 0 Then
            txtStream.WriteLine "[" & AgoraBR() & "] [VBS] [" & logLevel & "] " & messageText
            txtStream.Close
        End If
    End If

    Set txtStream = Nothing
    Err.Clear
    On Error GoTo 0
End Sub

Function TryGetFileSize(ByVal filePath, ByRef fileSize)
    On Error Resume Next

    fileSize = -1
    TryGetFileSize = False

    If Not fso.FileExists(filePath) Then
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If

    fileSize = fso.GetFile(filePath).Size
    TryGetFileSize = (Err.Number = 0)

    Err.Clear
    On Error GoTo 0
End Function

Function TryReadAllText(ByVal filePath, ByRef fileText)
    On Error Resume Next

    Dim txtStream
    fileText = ""
    TryReadAllText = False

    If Not fso.FileExists(filePath) Then
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If

    Set txtStream = fso.OpenTextFile(filePath, 1)
    If Err.Number <> 0 Then
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If

    fileText = txtStream.ReadAll
    txtStream.Close
    Set txtStream = Nothing

    TryReadAllText = True

    Err.Clear
    On Error GoTo 0
End Function

Sub CleanupExcelObjects(ByVal shouldSaveWorkbook)
    On Error Resume Next

    If Not wb Is Nothing Then
        If shouldSaveWorkbook Then
            wb.Save
        End If

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
    On Error GoTo 0
End Sub

Sub EncerrarComErro(ByVal exitCode, ByVal messageText)
    WriteLog "ERRO", messageText & " | elapsedSec=" & ElapsedSeconds()
    CleanupExcelObjects False
    WriteLog "INFO", "FIM - VBScript com erro. ExitCode=" & exitCode & " | elapsedSec=" & ElapsedSeconds()
    WriteLog "INFO", "========================================================="
    WScript.Quit exitCode
End Sub

Function ExtrairVersao(ByVal texto)
    On Error Resume Next

    Dim re
    Dim matches

    Set re = CreateObject("VBScript.RegExp")
    re.Pattern = "Vers[aã]o:\s*([^\r\n\|]+)"
    re.IgnoreCase = True
    re.Global = False

    If re.Test(texto) Then
        Set matches = re.Execute(texto)
        ExtrairVersao = Trim(matches(0).SubMatches(0))
    Else
        ExtrairVersao = ""
    End If

    Set matches = Nothing
    Set re = Nothing

    Err.Clear
    On Error GoTo 0
End Function

Function DetectarResultadoVba(ByVal newContent, ByRef successFlag, ByRef fatalFlag)
    successFlag = False
    fatalFlag = False
    DetectarResultadoVba = False

    If InStr(1, newContent, "ERRO FATAL", vbTextCompare) > 0 Then
        fatalFlag = True
        DetectarResultadoVba = True
        Exit Function
    End If

    If InStr(1, newContent, "FIM DO PROCESSO.", vbTextCompare) > 0 Then
        successFlag = (InStr(1, newContent, "Resultado=Sucesso", vbTextCompare) > 0)
        DetectarResultadoVba = True
    End If
End Function

Sub RunPostExecutionBat(ByVal batPath, ByVal currentExecId)
    If Len(batPath) = 0 Then
        Exit Sub
    End If

    If Not fso.FileExists(batPath) Then
        WriteLog "WARN", "Script pos-execucao nao encontrado: " & batPath
        Exit Sub
    End If

    On Error Resume Next

    Dim shellApp
    Dim cmdExe
    Dim commandLine
    Dim batExitCode

    Set shellApp = CreateObject("WScript.Shell")
    cmdExe = shellApp.ExpandEnvironmentStrings("%ComSpec%")

    If cmdExe = "" Or cmdExe = "%ComSpec%" Then
        cmdExe = "cmd.exe"
    End If

    commandLine = """" & cmdExe & """ /c """ & batPath & """ """ & currentExecId & """ AUTO"

    WriteLog "INFO", "Disparando BAT pos-execucao. ExecId=" & currentExecId & " | Comando=" & commandLine

    shellApp.CurrentDirectory = fso.GetParentFolderName(batPath)
    batExitCode = shellApp.Run(commandLine, 0, True)

    If batExitCode <> 0 Then
        WriteLog "WARN", "Script pos-execucao retornou ExitCode " & batExitCode
    End If

    WriteLog "INFO", "Pos-execucao concluida."

    Set shellApp = Nothing

    Err.Clear
    On Error GoTo 0
End Sub

' =============================================================================
' INICIO DA EXECUCAO
' =============================================================================
If WScript.Arguments.Count > 0 Then
    execId = CStr(WScript.Arguments(0))
Else
    execId = "MANUAL_" & GerarExecId()
End If

WriteLog "INFO", "========================================================="
WriteLog "INFO", "INICIO - Execucao via VBScript (Receitas Emitidas) [ExecId=" & execId & "]"
WriteLog "INFO", "Workbook=" & EXCEL_PATH

If Not fso.FileExists(EXCEL_PATH) Then
    EncerrarComErro 1, "Arquivo Excel nao encontrado: " & EXCEL_PATH
End If

Dim roboVersao
Dim initialLogSize
Dim currentLogSize
Dim previousLogSize
Dim fullLogContent
Dim newLogContent
Dim foundEnd
Dim successVba
Dim fatalVba
Dim waitStart
Dim versionText

roboVersao = "(desconhecida)"
initialLogSize = 0
currentLogSize = 0
previousLogSize = 0
fullLogContent = ""
newLogContent = ""
foundEnd = False
successVba = False
fatalVba = False
versionText = ""

If USE_TIMEOUT_MONITOR Then
    If Not EnsureLogFile(LOG_PATH_VBA) Then
        EncerrarComErro 8, "Falha ao preparar arquivo de log: " & LOG_PATH_VBA
    End If

    If Not TryGetFileSize(LOG_PATH_VBA, initialLogSize) Then
        EncerrarComErro 8, "Falha ao obter tamanho inicial do log: " & LOG_PATH_VBA
    End If

    WriteLog "INFO", "Monitoramento de Timeout Ativado. LogVBAInicial=" & initialLogSize & " bytes"
End If

On Error Resume Next
Set excelApp = CreateObject("Excel.Application")

If Err.Number <> 0 Or (excelApp Is Nothing) Then
    EncerrarComErro 2, "Falha ao iniciar Excel. Err=" & Err.Number
End If

excelApp.Visible = False
excelApp.DisplayAlerts = False
excelApp.ScreenUpdating = False
excelApp.EnableEvents = False
excelApp.AskToUpdateLinks = False

Set wb = excelApp.Workbooks.Open(EXCEL_PATH)

If Err.Number <> 0 Or (wb Is Nothing) Then
    EncerrarComErro 3, "Falha ao abrir workbook. Err=" & Err.Number
End If
If wb.ReadOnly Then
    EncerrarComErro 7, "Workbook aberto em modo somente leitura. Possivel bloqueio por outra instancia: " & EXCEL_PATH
End If

WriteLog "INFO", "Executando macro: " & MACRO_NAME
Err.Clear

excelApp.Run MACRO_NAME, execId

If Err.Number <> 0 Then
    EncerrarComErro 4, "Falha na execucao da macro. Err=" & Err.Number
End If

Err.Clear
On Error GoTo 0

If USE_TIMEOUT_MONITOR Then
    WriteLog "INFO", "Aguardando conclusao via leitura de Log (Max Timeout: " & MAX_TIMEOUT_SECONDS & "s)..."

    waitStart = Timer
    previousLogSize = initialLogSize

    Do While (Not foundEnd) And (SecondsSince(waitStart) < MAX_TIMEOUT_SECONDS)
        If TryGetFileSize(LOG_PATH_VBA, currentLogSize) Then
            If currentLogSize < previousLogSize Then
                WriteLog "WARN", "Log VBA truncado. Reiniciando baseline."
                initialLogSize = currentLogSize
                previousLogSize = currentLogSize
            ElseIf currentLogSize > previousLogSize Then
                If TryReadAllText(LOG_PATH_VBA, fullLogContent) Then
                    If Len(fullLogContent) > initialLogSize Then
                        newLogContent = Mid(fullLogContent, initialLogSize + 1)

                        versionText = ExtrairVersao(newLogContent)
                        If Len(versionText) > 0 Then
                            roboVersao = versionText
                        End If

                        foundEnd = DetectarResultadoVba(newLogContent, successVba, fatalVba)
                    End If
                Else
                    WriteLog "WARN", "Falha ao ler log durante monitoramento."
                End If

                previousLogSize = currentLogSize
            End If
        Else
            WriteLog "WARN", "Falha ao obter tamanho do log durante monitoramento."
        End If

        If Not foundEnd Then
            WScript.Sleep POLL_INTERVAL_MS
        End If
    Loop

    If Not foundEnd Then
        EncerrarComErro 5, "TIMEOUT: VBA nao registrou termino em " & MAX_TIMEOUT_SECONDS & "s"
    End If

    If fatalVba Or (Not successVba) Then
        EncerrarComErro 6, "VBA reportou falha/erro fatal nos logs"
    End If

    WriteLog "INFO", "VBA reportou sucesso (v" & roboVersao & ")"
Else
    successVba = True
    WriteLog "INFO", "Macro executada (Monitoramento offline)."
End If

CleanupExcelObjects True
RunPostExecutionBat POST_EXECUTION_BAT, execId

WriteLog "INFO", "FIM - VBScript com sucesso. elapsedSec=" & ElapsedSeconds()
WriteLog "INFO", "========================================================="
WScript.Quit 0
