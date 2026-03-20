Option Explicit

' =============================================================================
' RunMacro.vbs — Versão corrigida (fix quoting + ExitCode 255)
' Fluxo: VBS → Excel Macro → BAT → Node.js → WhatsApp
' =============================================================================

Dim excelApp, wb, fso, wsh
Dim excelPath, macroName, logPath
Dim batPath, execId, comandoBat
Dim scriptStart

excelPath = "C:\Automacoes\Receitas Bloqueadas\Receitas Bloqueadas.xlsm"
macroName = "ExecutarProcessoCompleto"
logPath   = "C:\Automacoes\Receitas Bloqueadas\Logs\Execution.log"
batPath   = "C:\Automacoes\Receitas Bloqueadas\RunWhatsApp.bat"

scriptStart = Timer

Set fso = CreateObject("Scripting.FileSystemObject")

' ---------------------------------------------------------------------------
' Função: timestamp no formato DD/MM/AAAA HH:MM:SS
' ---------------------------------------------------------------------------
Function AgoraBR()
    Dim d
    d = Now
    AgoraBR = Right("0" & Day(d), 2) & "/" & _
              Right("0" & Month(d), 2) & "/" & _
              Year(d) & " " & _
              Right("0" & Hour(d), 2) & ":" & _
              Right("0" & Minute(d), 2) & ":" & _
              Right("0" & Second(d), 2)
End Function

' ---------------------------------------------------------------------------
' Função: segundos decorridos desde início
' ---------------------------------------------------------------------------
Function ElapsedSeconds()
    Dim currentTimer, diff
    currentTimer = Timer
    diff = currentTimer - scriptStart
    If diff < 0 Then diff = diff + 86400
    ElapsedSeconds = Replace(FormatNumber(diff, 2, -1, 0, 0), ",", ".")
End Function

' ---------------------------------------------------------------------------
' Sub: garante que a pasta do log existe
' ---------------------------------------------------------------------------
Sub EnsureLogFolder()
    Dim parentFolder
    parentFolder = fso.GetParentFolderName(logPath)
    If parentFolder <> "" Then
        If Not fso.FolderExists(parentFolder) Then
            fso.CreateFolder parentFolder
        End If
    End If
End Sub

' ---------------------------------------------------------------------------
' Sub: grava linha no log consolidado (com fallback silencioso)
' ---------------------------------------------------------------------------
Sub WriteLog(level, msg)
    Dim txtStream
    On Error Resume Next
    EnsureLogFolder
    Set txtStream = fso.OpenTextFile(logPath, 8, True)
    If Err.Number = 0 Then
        txtStream.WriteLine "[" & AgoraBR() & "] [VBS] [" & level & "] " & msg
        txtStream.Close
    End If
    Err.Clear
    On Error GoTo 0
End Sub

' ---------------------------------------------------------------------------
' Função: gera ExecId único baseado em timestamp
' ---------------------------------------------------------------------------
Function GerarExecId()
    Dim d
    d = Now
    GerarExecId = Year(d) & _
                  Right("0" & Month(d), 2) & _
                  Right("0" & Day(d), 2) & "_" & _
                  Right("0" & Hour(d), 2) & _
                  Right("0" & Minute(d), 2) & _
                  Right("0" & Second(d), 2)
End Function

' ---------------------------------------------------------------------------
' Sub: limpa objetos Excel com segurança
' ---------------------------------------------------------------------------
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
    On Error GoTo 0
End Sub

' ---------------------------------------------------------------------------
' Sub: encerra com erro — grava log e sai com código específico
' ---------------------------------------------------------------------------
Sub EncerrarComErro(exitCode, msg)
    WriteLog "ERRO", msg & " | elapsedSec=" & ElapsedSeconds()
    Call LimparObjetosExcel()
    WriteLog "INFO", "FIM - VBScript com erro. ExitCode=" & exitCode & " | elapsedSec=" & ElapsedSeconds()
    WriteLog "INFO", "========================================================="
    WScript.Quit exitCode
End Sub

' =============================================================================
' INÍCIO DA EXECUÇÃO
' =============================================================================

WriteLog "INFO", "========================================================="
WriteLog "INFO", "INICIO - Execução via VBScript"
WriteLog "INFO", "Workbook=" & excelPath
WriteLog "INFO", "Macro=" & macroName
WriteLog "INFO", "BAT=" & batPath
WriteLog "INFO", "WScript.Version=" & WScript.Version & " | ScriptName=" & WScript.ScriptName

' ---------------------------------------------------------------------------
' Validações iniciais
' ---------------------------------------------------------------------------
If Not fso.FileExists(excelPath) Then
    Call EncerrarComErro(1, "Arquivo Excel não encontrado: " & excelPath)
End If

If Not fso.FileExists(batPath) Then
    WriteLog "WARN", "RunWhatsApp.bat não encontrado em: " & batPath & " | O fluxo WhatsApp será ignorado."
End If

' ---------------------------------------------------------------------------
' Iniciar Excel
' ---------------------------------------------------------------------------
On Error Resume Next

WriteLog "INFO", "Iniciando Excel.Application..."
Set excelApp = CreateObject("Excel.Application")

If Err.Number <> 0 Or (excelApp Is Nothing) Then
    Call EncerrarComErro(2, "Falha ao iniciar Excel.Application. Err=" & Err.Number & " Desc=" & Err.Description)
End If

Err.Clear
excelApp.Visible       = False
excelApp.DisplayAlerts = False
excelApp.ScreenUpdating = False
excelApp.EnableEvents  = False
excelApp.AskToUpdateLinks = False
WriteLog "INFO", "Excel iniciado com sucesso. Visible=False DisplayAlerts=False EnableEvents=False"

' ---------------------------------------------------------------------------
' Abrir workbook
' ---------------------------------------------------------------------------
WriteLog "INFO", "Abrindo pasta de trabalho..."
Err.Clear
Set wb = excelApp.Workbooks.Open(excelPath)

If Err.Number <> 0 Or (wb Is Nothing) Then
    Call EncerrarComErro(3, "Falha ao abrir workbook. Err=" & Err.Number & " Desc=" & Err.Description)
End If

WriteLog "INFO", "Workbook aberto com sucesso: " & wb.Name

' ---------------------------------------------------------------------------
' Executar macro
' ---------------------------------------------------------------------------
WriteLog "INFO", "Executando macro: " & macroName
Err.Clear
excelApp.Run macroName

If Err.Number <> 0 Then
    Call EncerrarComErro(4, "Falha na execução da macro. Err=" & Err.Number & " Desc=" & Err.Description)
Else
    WriteLog "INFO", "Macro executada com sucesso."
End If

' ---------------------------------------------------------------------------
' Fechar workbook
' ---------------------------------------------------------------------------
WriteLog "INFO", "Fechando workbook sem salvar alterações adicionais no VBS..."
Err.Clear
wb.Close False

If Err.Number <> 0 Then
    Call EncerrarComErro(5, "Falha ao fechar workbook. Err=" & Err.Number & " Desc=" & Err.Description)
End If

Set wb = Nothing
WriteLog "INFO", "Workbook fechado com sucesso."

' ---------------------------------------------------------------------------
' Fechar Excel
' ---------------------------------------------------------------------------
WriteLog "INFO", "Fechando Excel..."
Err.Clear
excelApp.Quit

If Err.Number <> 0 Then
    Set excelApp = Nothing
    Call EncerrarComErro(6, "Falha ao fechar Excel. Err=" & Err.Number & " Desc=" & Err.Description)
End If

Set excelApp = Nothing
WriteLog "INFO", "Excel finalizado com sucesso."

' ---------------------------------------------------------------------------
' Disparar BAT
' ---------------------------------------------------------------------------
execId = GerarExecId()
WriteLog "INFO", "ExecId gerado: " & execId

If fso.FileExists(batPath) Then

    ' -------------------------------------------------------------------------
    ' CORREÇÃO CRÍTICA:
    ' %ComSpec% NÃO é expandido pelo VBScript nativamente.
    ' Usar WScript.Shell.ExpandEnvironmentStrings para obter o caminho real
    ' do cmd.exe antes de montar o comando.
    ' Sem isso, o Run() recebe o literal "%ComSpec%" → cmd parser falha → ExitCode 255.
    ' -------------------------------------------------------------------------
    Dim wshTemp
    Set wshTemp = CreateObject("WScript.Shell")

    Dim cmdExe
    cmdExe = wshTemp.ExpandEnvironmentStrings("%ComSpec%")
    Set wshTemp = Nothing

    If cmdExe = "" Or cmdExe = "%ComSpec%" Then
        cmdExe = "cmd.exe"
        WriteLog "WARN", "AVISO: ExpandEnvironmentStrings retornou vazio para %ComSpec%. Usando fallback: cmd.exe"
    End If

    WriteLog "INFO", "Shell resolvido: " & cmdExe

    ' Montar o comando com quoting correto para WScript.Shell.Run:
    ' O CMD /c remove o primeiro e último caracter de aspas SE houver múltiplas aspas.
    ' Para rotas com espaço, é OBRIGATÓRIO envolver tudo após o /c num par de aspas extras.
    comandoBat = """" & cmdExe & """ /c """"" & batPath & """ """ & execId & """ AUTO"""

    WriteLog "INFO", "Disparando BAT de forma síncronA e oculta."
    WriteLog "INFO", "Cmd resolvido: " & cmdExe
    WriteLog "INFO", "Comando completo: " & comandoBat
    WriteLog "INFO", "WorkingDir: " & fso.GetParentFolderName(batPath)

    Set wsh = CreateObject("WScript.Shell")

    If Err.Number <> 0 Or (wsh Is Nothing) Then
        Call EncerrarComErro(7, "Falha ao criar WScript.Shell para disparar BAT. Err=" & Err.Number & " Desc=" & Err.Description)
    End If

    Err.Clear
    wsh.CurrentDirectory = fso.GetParentFolderName(batPath)

    Dim batExitCode
    Err.Clear

    ' Run(strCommand, intWindowStyle, bWaitOnReturn)
    ' intWindowStyle = 0  → janela oculta
    ' bWaitOnReturn  = True → síncrono (captura exitcode)
    batExitCode = wsh.Run(comandoBat, 0, True)

    If Err.Number <> 0 Then
        Dim runErr, runDesc
        runErr  = Err.Number
        runDesc = Err.Description
        Set wsh = Nothing
        Call EncerrarComErro(8, "Falha ao executar BAT via WScript.Shell.Run. Err=" & runErr & " Desc=" & runDesc)
    End If

    Set wsh = Nothing

    WriteLog "INFO", "BAT finalizado. ExitCode=" & batExitCode & " ExecId=" & execId

    If batExitCode <> 0 Then
        WriteLog "WARN", "AVISO: BAT retornou ExitCode diferente de zero. Verifique logs [BAT] e [NODE]. ExitCode=" & batExitCode
    End If

Else
    WriteLog "WARN", "AVISO: WhatsApp não foi disparado — BAT não encontrado: " & batPath
End If

' ---------------------------------------------------------------------------
' Fim
' ---------------------------------------------------------------------------
WriteLog "INFO", "FIM - VBScript com sucesso. elapsedSec=" & ElapsedSeconds()
WriteLog "INFO", "========================================================="
WScript.Quit 0