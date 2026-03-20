Option Explicit

' =============================================================================
' Trigger_Automation.vbs (TEMPLATE)
' Descrição: Script padrão para disparar macros Excel com logging estruturado.
' =============================================================================

Dim excelApp, wb, fso
Dim excelPath, macroName, logPath
Dim scriptStart

' ---------- CONFIGURAÇÕES DO MÓDULO ----------
' Edite os caminhos abaixo conforme necessário:
excelPath = "C:\Automacoes\_Template\NOME_DA_SUA_PLANILHA.xlsm"
macroName = "ExecutarProcesso"
logPath   = "C:\Automacoes\_Template\Logs\Execution.log"
' ---------------------------------------------

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
' Sub: grava linha no log consolidado
' ---------------------------------------------------------------------------
Sub WriteLog(level, msg)
    Dim txtStream
    On Error Resume Next
    Set txtStream = fso.OpenTextFile(logPath, 8, True)
    If Err.Number = 0 Then
        txtStream.WriteLine "[" & AgoraBR() & "] [VBS] [" & level & "] " & msg
        txtStream.Close
    End If
    Err.Clear
    On Error GoTo 0
End Sub

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
        excelApp.Quit
        Set excelApp = Nothing
    End If
    Err.Clear
    On Error GoTo 0
End Sub

' ---------------------------------------------------------------------------
' Sub: encerra com erro
' ---------------------------------------------------------------------------
Sub EncerrarComErro(exitCode, msg)
    WriteLog "ERRO", msg & " | elapsedSec=" & ElapsedSeconds()
    Call LimparObjetosExcel()
    WriteLog "INFO", "FIM - VBScript com erro. ExitCode=" & exitCode
    WScript.Quit exitCode
End Sub

' =============================================================================
' INÍCIO DA EXECUÇÃO
' =============================================================================

WriteLog "INFO", "========================================================="
WriteLog "INFO", "INICIO - Execução via VBScript (TEMPLATE)"
WriteLog "INFO", "Workbook=" & excelPath

If Not fso.FileExists(excelPath) Then
    Call EncerrarComErro(1, "Arquivo Excel não encontrado: " & excelPath)
End If

On Error Resume Next
Set excelApp = CreateObject("Excel.Application")
If Err.Number <> 0 Or (excelApp Is Nothing) Then
    Call EncerrarComErro(2, "Falha ao iniciar Excel. Err=" & Err.Number)
End If

excelApp.Visible = False
excelApp.DisplayAlerts = False

Set wb = excelApp.Workbooks.Open(excelPath)
If Err.Number <> 0 Or (wb Is Nothing) Then
    Call EncerrarComErro(3, "Falha ao abrir workbook. Err=" & Err.Number)
End If

WriteLog "INFO", "Executando macro: " & macroName
excelApp.Run macroName

If Err.Number <> 0 Then
    Call EncerrarComErro(4, "Falha na execução da macro. Err=" & Err.Number)
Else
    WriteLog "INFO", "Macro executada com sucesso."
End If

wb.Close False
excelApp.Quit
Set wb = Nothing
Set excelApp = Nothing

WriteLog "INFO", "FIM - VBScript com sucesso. elapsedSec=" & ElapsedSeconds()
WriteLog "INFO", "========================================================="
WScript.Quit 0
