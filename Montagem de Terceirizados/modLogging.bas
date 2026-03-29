Attribute VB_Name = "modLogging"
Option Explicit

' ====================================================================================
' PRIVADOS (ESTADO)
' ====================================================================================
Private m_strRunId      As String
Private m_blnInLogWrite As Boolean
Private m_strStepName   As String
Private m_dblStepT0     As Double

' ====================================================================================
' RUN ID
' ====================================================================================
Public Sub IniciarRunId(Optional ByVal blnForcar As Boolean = False)
    If blnForcar Or Len(m_strRunId) = 0 Then
        Randomize
        m_strRunId = Format$(Now, "yyyymmdd_hhnnss") & "_" & Format$(Int(Rnd() * 9999), "0000")
    End If
End Sub

Public Function GetRunId() As String
    If Len(m_strRunId) = 0 Then IniciarRunId
    GetRunId = m_strRunId
End Function

Public Sub DefinirRunId(ByVal strRunId As String)
    Dim strLimpo As String
    strLimpo = Trim$(strRunId)

    If Len(strLimpo) > 0 Then
        m_strRunId = strLimpo
    End If
End Sub

' ====================================================================================
' STEPS
' ====================================================================================
Public Sub LogStepStart(ByVal strStep As String)
    m_strStepName = strStep
    m_dblStepT0   = Timer
    GravarLogEx "Iniciando etapa: " & strStep, LOG_DEBUG
End Sub

Public Sub LogStepEnd(ByVal strResultado As String)
    Dim dblElapsed As Double
    dblElapsed = TimerElapsed(m_dblStepT0)
    GravarLogEx "Finalizado: " & m_strStepName & " | Result: " & strResultado & " | Tempo: " & Format$(dblElapsed, "0.00") & "s", LOG_INFO
    m_strStepName = ""
End Sub

' ====================================================================================
' CORE LOGGING (ASCII SAFE)
' ====================================================================================
Public Sub GravarLogEx(ByVal strMensagem As String, Optional ByVal lngNivel As Long = LOG_INFO)
    Dim strLinha     As String
    Dim strArquivo   As String
    Dim intFileNum   As Integer
    
    If m_blnInLogWrite Then Exit Sub ' Evita recursao infinita em caso de erro no proprio log
    m_blnInLogWrite = True
    
    On Error GoTo TratarErro
    IniciarRunId
    
    ' 1. Formatar Mensagem
    strLinha = "[" & Format$(Now, "yyyy-mm-dd hh:mm:ss") & "] [" & NivelToString(lngNivel) & "] [Run:" & m_strRunId & "] " & strMensagem
    
    ' 2. Caminho do Log
    strArquivo = ThisWorkbook.Path & "\Logs\log_" & Format$(Now, "yyyy-mm-dd") & ".log"
    
    On Error Resume Next
    If Dir$(ThisWorkbook.Path & "\Logs", vbDirectory) = "" Then MkDir ThisWorkbook.Path & "\Logs"
    On Error GoTo TratarErro

    ' 3. Escrita (Append)
    intFileNum = FreeFile
    Open strArquivo For Append Shared As #intFileNum
    Print #intFileNum, strLinha
    Close #intFileNum
    
    Debug.Print strLinha

Saida:
    m_blnInLogWrite = False
    Exit Sub

TratarErro:
    On Error Resume Next
    Debug.Print "FALHA GRAVE LOG: " & strMensagem & " | " & Err.Description
    Resume Saida
End Sub

Private Function NivelToString(ByVal lngNivel As Long) As String
    Select Case lngNivel
        Case LOG_DEBUG:   NivelToString = "DEBUG"
        Case LOG_INFO:    NivelToString = "INFO "
        Case LOG_WARNING: NivelToString = "WARN "
        Case LOG_ERROR:   NivelToString = "ERROR"
        Case Else:        NivelToString = "LOG  "
    End Select
End Function
