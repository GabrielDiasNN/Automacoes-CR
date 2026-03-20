Option Explicit

' ==============================================================================
' ARQUIVO: ExecutarMacros.vbs
' VERSÃO: 2.0
' DESCRIÇÃO: Disparador da macro "AtualizarEEnviarOutlook" com tratamento de erro
' ==============================================================================

Dim excelApp, wb, fso
Dim excelPath, macroName, logPath, baseFolder
Dim scriptStart

' ---------- CONFIGURAÇÕES ----------
excelPath = "C:\Automacoes\Receitas Emitidas\Controle de Receitas Emitidas.xlsm"
macroName = "AtualizarEEnviarOutlook"
baseFolder = "C:\Automacoes\Receitas Emitidas"
logPath   = baseFolder & "\Logs\Execution.log"

scriptStart = Timer
Set fso = CreateObject("Scripting.FileSystemObject")

' ---------- FUNÇÕES AUXILIARES ----------

Function AgoraBR()
    Dim d
    d = Now
    AgoraBR = Right("0" & Day(d), 2) & "/" & Right("0" & Month(d), 2) & "/" & Year(d) & " " & _
              Right("0" & Hour(d), 2) & ":" & Right("0" & Minute(d), 2) & ":" & Right("0" & Second(d), 2)
End Function

Function ElapsedSeconds()
    Dim diff
    diff = Timer - scriptStart
    If diff < 0 Then diff = diff + 86400
    ElapsedSeconds = FormatNumber(diff, 2)
End Function

Sub WriteLog(level, msg)
    Dim ts, parent
    On Error Resume Next
    parent = fso.GetParentFolderName(logPath)
    If Not fso.FolderExists(parent) Then fso.CreateFolder(parent)
    
    Set ts = fso.OpenTextFile(logPath, 8, True)
    If Err.Number = 0 Then
        ts.WriteLine "[" & AgoraBR() & "] [VBS] [" & level & "] " & msg
        ts.Close
    End If
    Err.Clear
End Sub

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
End Sub

Sub EncerrarComErro(exitCode, msg)
    WriteLog "ERROR", msg & " (Tempo: " & ElapsedSeconds() & "s)"
    Call LimparObjetosExcel()
    WriteLog "INFO", "Execução encerrada com erro [" & exitCode & "]"
    WScript.Quit exitCode
End Sub

' ==============================================================================
' INÍCIO DA EXECUÇÃO
' ==============================================================================

WriteLog "INFO", "------------------------------------------------------------"
WriteLog "INFO", "Iniciando automação: " & WScript.ScriptName
WriteLog "INFO", "Arquivo: " & excelPath

' 1. Pre-flight checks
If Not fso.FileExists(excelPath) Then
    Call EncerrarComErro(1, "Arquivo Excel não encontrado.")
End If

' 2. Iniciar Excel
On Error Resume Next
WriteLog "INFO", "Abrindo Excel.Application..."
Set excelApp = CreateObject("Excel.Application")
If Err.Number <> 0 Or excelApp Is Nothing Then
    Call EncerrarComErro(2, "Falha ao criar instância do Excel: " & Err.Description)
End If

excelApp.Visible = False
excelApp.DisplayAlerts = False

' 3. Abrir Workbook
WriteLog "INFO", "Abrindo planilha..."
Set wb = excelApp.Workbooks.Open(excelPath)
If Err.Number <> 0 Or wb Is Nothing Then
    Call EncerrarComErro(3, "Falha ao abrir a planilha: " & Err.Description)
End If

' 4. Executar Macro
WriteLog "INFO", "Executando macro: " & macroName
excelApp.Run "'" & wb.Name & "'!" & macroName
If Err.Number <> 0 Then
    Call EncerrarComErro(4, "Falha ao executar a macro: " & Err.Description)
End If

' 5. Salvar e Fechar
WriteLog "INFO", "Salvando alterações..."
wb.Save
If Err.Number <> 0 Then
    WriteLog "WARN", "Erro ao salvar planilha: " & Err.Description
End If

WriteLog "INFO", "Finalizando processos..."
Call LimparObjetosExcel()

WriteLog "INFO", "Automação finalizada com sucesso (Tempo: " & ElapsedSeconds() & "s)"
WriteLog "INFO", "------------------------------------------------------------"
WScript.Quit 0