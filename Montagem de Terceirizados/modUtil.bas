Attribute VB_Name = "modUtil"
Option Explicit

' ====================================================================================
' DATA / HORA
' ====================================================================================
Public Function FormatarDataBR(ByVal dtmValor As Date, Optional ByVal blnIncluirHora As Boolean = False) As String
    If blnIncluirHora Then
        FormatarDataBR = Format$(dtmValor, "dd/mm/yyyy hh:mm:ss")
    Else
        FormatarDataBR = Format$(dtmValor, "dd/mm/yyyy")
    End If
End Function

Public Function TimerElapsed(ByVal dblT0 As Double) As Double
    Dim dblT As Double
    dblT = Timer
    ' Tratamento de cruzamento de meia-noite (Timer reseta para 0)
    TimerElapsed = IIf(dblT >= dblT0, dblT - dblT0, (86400# - dblT0) + dblT)
End Function

' ====================================================================================
' HASH / IDENTIDADE
' ====================================================================================
Public Function GerarHashDJB2(ByVal strTexto As String) As String
    Dim lngI    As Long
    Dim lngHash As Long
    
    lngHash = 5381
    For lngI = 1 To Len(strTexto)
        lngHash = ((lngHash * 33) + Asc(Mid$(strTexto, lngI, 1))) And &H7FFFFFFF
    Next lngI
    
    GerarHashDJB2 = Hex$(lngHash)
End Function

' ====================================================================================
' HTML
' ====================================================================================
Public Function HTMLEncode(ByVal strTexto As String) As String
    Dim strRes As String
    strRes = strTexto
    strRes = Replace(strRes, "&", "&amp;")
    strRes = Replace(strRes, "<", "&lt;")
    strRes = Replace(strRes, ">", "&gt;")
    strRes = Replace(strRes, """", "&quot;")
    strRes = Replace(strRes, "'", "&#39;")
    HTMLEncode = strRes
End Function

' ====================================================================================
' HELPERS
' ====================================================================================
Public Function WorksheetExists(ByVal strName As String) As Boolean
    Dim objWs As Worksheet
    On Error Resume Next
    Set objWs = ThisWorkbook.Worksheets(strName)
    WorksheetExists = (Not objWs Is Nothing)
    On Error GoTo 0
End Function