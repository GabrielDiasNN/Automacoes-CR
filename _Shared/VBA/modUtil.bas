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
    Dim lngI As Long
    Dim lngCode As Long
    Dim dblHash As Double
    Dim dblModulo As Double

    dblModulo = 2147483647#
    dblHash = 5381#
    For lngI = 1 To Len(strTexto)
        lngCode = AscW(Mid$(strTexto, lngI, 1))
        If lngCode < 0 Then lngCode = lngCode + 65536

        dblHash = (dblHash * 33#) + CDbl(lngCode)
        dblHash = dblHash - (Fix(dblHash / dblModulo) * dblModulo)
        If dblHash < 0# Then dblHash = dblHash + dblModulo
    Next lngI

    GerarHashDJB2 = Hex$(CLng(dblHash))
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
