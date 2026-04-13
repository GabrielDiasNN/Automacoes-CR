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
        m_strRunId = NormalizeRunId(Format$(Now, "yyyymmdd_hhnnss") & "_" & Format$(Int(Rnd() * 9999), "0000"))
    End If
End Sub

Public Function GetRunId() As String
    If Len(m_strRunId) = 0 Then IniciarRunId
        GetRunId = m_strRunId
End Function

Public Sub DefinirRunId(ByVal strRunId As String)
    Dim strLimpo As String
    strLimpo = NormalizeRunId(strRunId)

    If Len(strLimpo) > 0 Then
        m_strRunId = strLimpo
    End If
End Sub

Private Function NormalizeRunId(ByVal strValue As String) As String
    Dim strIn      As String
    Dim strOut     As String
    Dim lngI       As Long
    Dim strCh      As String
    Dim intCode    As Integer

    strIn = Trim$(strValue)
    If Len(strIn) = 0 Then
        NormalizeRunId = ""
     Exit Function
    End If

    For lngI = 1 To Len(strIn)
        strCh = Mid$(strIn, lngI, 1)
        intCode = Asc(strCh)

        If (intCode >= 48 And intCode <= 57) _
            Or (intCode >= 65 And intCode <= 90) _
            Or (intCode >= 97 And intCode <= 122) _
            Or strCh = "_" _
            Or strCh = "-" Then
            strOut = strOut & strCh
        Else
            strOut = strOut & "_"
        End If
    Next lngI

    If Len(strOut) > 64 Then strOut = Left$(strOut, 64)
        NormalizeRunId = strOut
End Function

' ====================================================================================
' STEPS
' ====================================================================================
Public Sub LogStepStart(ByVal strStep As String)
    m_strStepName = strStep
    m_dblStepT0 = Timer
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
            strLinha = "[" & Format$(Now, "dd/mm/yyyy hh:mm:ss") & "] [VBA] [" & NivelToString(lngNivel) & "] [ExecId:" & m_strRunId & "] " & SanitizarMensagemLog(strMensagem)

            ' 2. Caminho Do Log
            strArquivo = ThisWorkbook.Path & "\Logs\Montagem.log"

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

Private Function SanitizarMensagemLog(ByVal strMensagem As String) As String
    Dim strTexto As String
    Dim strOut As String
    Dim strCh As String
    Dim lngI As Long
    Dim lngCode As Long

    strTexto = Trim$(strMensagem)
    strTexto = Replace(strTexto, vbCrLf, " ")
    strTexto = Replace(strTexto, vbCr, " ")
    strTexto = Replace(strTexto, vbLf, " ")
    strTexto = RemoveDiacritics(strTexto)

    For lngI = 1 To Len(strTexto)
        strCh = Mid$(strTexto, lngI, 1)
        lngCode = AscW(strCh)
        If lngCode < 0 Then lngCode = lngCode + 65536

            If lngCode = 9 Or (lngCode >= 32 And lngCode <= 126) Then
                strOut = strOut & strCh
            ElseIf lngCode = 160 Then
                strOut = strOut & " "
            Else
                strOut = strOut & "_"
            End If
        Next lngI

        Do While InStr(strOut, "  ") > 0
            strOut = Replace(strOut, "  ", " ")
        Loop

        SanitizarMensagemLog = Trim$(strOut)
End Function

Private Function RemoveDiacritics(ByVal strTexto As String) As String
    Dim strOut As String

    strOut = strTexto
    strOut = Replace(strOut, ChrW$(192), "A")
    strOut = Replace(strOut, ChrW$(193), "A")
    strOut = Replace(strOut, ChrW$(194), "A")
    strOut = Replace(strOut, ChrW$(195), "A")
    strOut = Replace(strOut, ChrW$(196), "A")
    strOut = Replace(strOut, ChrW$(199), "C")
    strOut = Replace(strOut, ChrW$(200), "E")
    strOut = Replace(strOut, ChrW$(201), "E")
    strOut = Replace(strOut, ChrW$(202), "E")
    strOut = Replace(strOut, ChrW$(203), "E")
    strOut = Replace(strOut, ChrW$(204), "I")
    strOut = Replace(strOut, ChrW$(205), "I")
    strOut = Replace(strOut, ChrW$(206), "I")
    strOut = Replace(strOut, ChrW$(207), "I")
    strOut = Replace(strOut, ChrW$(210), "O")
    strOut = Replace(strOut, ChrW$(211), "O")
    strOut = Replace(strOut, ChrW$(212), "O")
    strOut = Replace(strOut, ChrW$(213), "O")
    strOut = Replace(strOut, ChrW$(214), "O")
    strOut = Replace(strOut, ChrW$(217), "U")
    strOut = Replace(strOut, ChrW$(218), "U")
    strOut = Replace(strOut, ChrW$(219), "U")
    strOut = Replace(strOut, ChrW$(220), "U")
    strOut = Replace(strOut, ChrW$(221), "Y")
    strOut = Replace(strOut, ChrW$(224), "a")
    strOut = Replace(strOut, ChrW$(225), "a")
    strOut = Replace(strOut, ChrW$(226), "a")
    strOut = Replace(strOut, ChrW$(227), "a")
    strOut = Replace(strOut, ChrW$(228), "a")
    strOut = Replace(strOut, ChrW$(231), "c")
    strOut = Replace(strOut, ChrW$(232), "e")
    strOut = Replace(strOut, ChrW$(233), "e")
    strOut = Replace(strOut, ChrW$(234), "e")
    strOut = Replace(strOut, ChrW$(235), "e")
    strOut = Replace(strOut, ChrW$(236), "i")
    strOut = Replace(strOut, ChrW$(237), "i")
    strOut = Replace(strOut, ChrW$(238), "i")
    strOut = Replace(strOut, ChrW$(239), "i")
    strOut = Replace(strOut, ChrW$(242), "o")
    strOut = Replace(strOut, ChrW$(243), "o")
    strOut = Replace(strOut, ChrW$(244), "o")
    strOut = Replace(strOut, ChrW$(245), "o")
    strOut = Replace(strOut, ChrW$(246), "o")
    strOut = Replace(strOut, ChrW$(249), "u")
    strOut = Replace(strOut, ChrW$(250), "u")
    strOut = Replace(strOut, ChrW$(251), "u")
    strOut = Replace(strOut, ChrW$(252), "u")
    strOut = Replace(strOut, ChrW$(253), "y")
    strOut = Replace(strOut, ChrW$(255), "y")

    RemoveDiacritics = strOut
End Function

Private Function NivelToString(ByVal lngNivel As Long) As String
    Select Case lngNivel
     Case LOG_DEBUG:   NivelToString = "DEBUG"
     Case LOG_INFO:    NivelToString = "INFO"
     Case LOG_WARNING: NivelToString = "WARN"
     Case LOG_ERROR:   NivelToString = "ERROR"
     Case Else:        NivelToString = "INFO"
    End Select
End Function

' ====================================================================================
' SMOKE TEST - Executar via VBE sem disparar o processo principal
' ====================================================================================
Public Sub TestarLogger()
    Dim idSaida As String

    DefinirRunId "Teste RunId #01 & Tag!"
    idSaida = GetRunId()

    Debug.Print "=== TestarLogger: modLogging ==="
    Debug.Print "RunId  : [" & idSaida & "]"

    LogStepStart "SMOKE"
    GravarLogEx "Linha 1 - mensagem simples", LOG_INFO
    GravarLogEx "Linha 2 - chars especiais: & < > ; -- Select 1", LOG_INFO
    GravarLogEx "Linha 3 - nivel WARN", LOG_WARNING
    GravarLogEx "Linha 4 - nivel ERROR", LOG_ERROR
    LogStepEnd "OK"

    Debug.Print "Concluido. Verifique a pasta Logs."
End Sub
