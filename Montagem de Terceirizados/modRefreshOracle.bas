Attribute VB_Name = "modRefreshOracle"
Option Explicit

' ====================================================================================
' STAMP HELPERS
' ====================================================================================
Public Sub EnsureStampNamedRange()
    Dim objLo     As ListObject
    Dim strRefers As String

    Set objLo = FindListObjectByName(STAMP_TABLE_NAME)
    If objLo Is Nothing Then
        Err.Raise vbObjectError + 801, "EnsureStampNamedRange", "Tabela '" & STAMP_TABLE_NAME & "' nao encontrada."
    End If
    
    If Not ListObjectHasColumn(objLo, STAMP_COLUMN_HEADER) Then
        Err.Raise vbObjectError + 802, "EnsureStampNamedRange", "Coluna '" & STAMP_COLUMN_HEADER & "' nao existe em '" & STAMP_TABLE_NAME & "'."
    End If

    strRefers = "=IFERROR(INDEX(" & STAMP_TABLE_NAME & "[" & STAMP_COLUMN_HEADER & "],1),"""")"
    
    On Error Resume Next
    ThisWorkbook.Names(STAMP_NAMED_RANGE).Delete
    On Error GoTo 0
    
    ThisWorkbook.Names.Add Name:=STAMP_NAMED_RANGE, RefersTo:=strRefers
    GravarLogEx "STAMP NamedRange '" & STAMP_NAMED_RANGE & "' => " & strRefers, LOG_DEBUG
End Sub

Public Function GetStampValue() As Variant
    On Error GoTo Fallback
    Dim objLo As ListObject
    Dim objLc As ListColumn

    Set objLo = FindListObjectByName(STAMP_TABLE_NAME)
    If objLo Is Nothing Then GoTo Fallback
    
    If objLo.ListRows.count = 0 Or objLo.DataBodyRange Is Nothing Then
        GetStampValue = Empty: Exit Function
    End If
    
    On Error Resume Next
    Set objLc = objLo.ListColumns(STAMP_COLUMN_HEADER)
    On Error GoTo Fallback
    
    If objLc Is Nothing Then GoTo Fallback
    If objLc.DataBodyRange Is Nothing Then GetStampValue = Empty: Exit Function
    
    GetStampValue = objLc.DataBodyRange.Cells(1, 1).Value2
    Exit Function

Fallback:
    Dim objNm As Name
    On Error Resume Next
    Set objNm = ThisWorkbook.Names(STAMP_NAMED_RANGE)
    If Not objNm Is Nothing Then
        If Not objNm.RefersToRange Is Nothing Then
            GetStampValue = objNm.RefersToRange.Value2
            Exit Function
        End If
    End If
    On Error GoTo 0
    GetStampValue = Empty
End Function

Public Function StampKey(ByVal varValue As Variant) As String
    On Error GoTo Fallback
    If IsEmpty(varValue) Then StampKey = "": Exit Function
    If IsNumeric(varValue) Then StampKey = "N:" & Format$(CDbl(varValue), "0.0000000000"): Exit Function
    If IsDate(varValue) Then StampKey = "D:" & Format$(CDbl(CDate(varValue)), "0.0000000000"): Exit Function
    
    StampKey = "S:" & Trim$(CStr(varValue))
    Exit Function
    
Fallback:
    StampKey = "S:" & Trim$(CStr(varValue))
End Function

Public Sub LogStampSnapshot(ByVal strMarcador As String, ByVal varValue As Variant)
    GravarLogEx "Carimbo (" & STAMP_TABLE_NAME & "." & STAMP_COLUMN_HEADER & ") " & _
                UCase$(Trim$(strMarcador)) & ": " & StampValorParaLog(varValue) & " | Key=" & StampKey(varValue), LOG_DEBUG
End Sub

Public Function IsStampInconclusivoPorTabelaVazia() As Boolean
    Dim objLo As ListObject
    Set objLo = FindListObjectByName(STAMP_TABLE_NAME)
    If objLo Is Nothing Then
        IsStampInconclusivoPorTabelaVazia = False
    Else
        IsStampInconclusivoPorTabelaVazia = (objLo.ListRows.count = 0)
    End If
End Function

Private Function StampValorParaLog(ByVal varValue As Variant) As String
    Dim dtmVal As Date
    Dim dblVal  As Double
    
    On Error GoTo Falha
    If IsEmpty(varValue) Then StampValorParaLog = "(vazio)": Exit Function
    If IsError(varValue) Then StampValorParaLog = "(erro)":  Exit Function
    If IsDate(varValue) Then StampValorParaLog = FormatarDataBR(CDate(varValue), True): Exit Function
    
    If IsNumeric(varValue) Then
        dblVal = CDbl(varValue)
        On Error Resume Next
        dtmVal = CDate(dblVal)
        On Error GoTo Falha
        
        If Year(dtmVal) >= 2000 And Year(dtmVal) <= 2100 Then
            StampValorParaLog = FormatarDataBR(dtmVal, True) & " (serial=" & Format$(dblVal, "0.000000") & ")"
        Else
            StampValorParaLog = CStr(varValue)
        End If
        Exit Function
    End If
    
    StampValorParaLog = Trim$(CStr(varValue))
    Exit Function
    
Falha:
    StampValorParaLog = Trim$(CStr(varValue))
End Function

' ====================================================================================
' HELPERS DE ESTRUTURA
' ====================================================================================
Public Function FindListObjectByName(ByVal strListName As String) As ListObject
    Dim objWs As Worksheet
    Dim objLo As ListObject
    For Each objWs In ThisWorkbook.Worksheets
        For Each objLo In objWs.ListObjects
            If StrComp(objLo.Name, strListName, vbTextCompare) = 0 Then
                Set FindListObjectByName = objLo: Exit Function
            End If
        Next objLo
    Next objWs
End Function

Public Function ListObjectHasColumn(ByVal objLo As ListObject, ByVal strColHeader As String) As Boolean
    Dim objLc As ListColumn
    For Each objLc In objLo.ListColumns
        If StrComp(CStr(objLc.Name), strColHeader, vbTextCompare) = 0 Then
            ListObjectHasColumn = True: Exit Function
        End If
    Next objLc
End Function

Public Function FindConnectionByPartialName(ByVal strPartialName As String) As WorkbookConnection
    Dim objConn As WorkbookConnection
    For Each objConn In ThisWorkbook.Connections
        If InStr(1, objConn.Name, strPartialName, vbTextCompare) > 0 Then
            Set FindConnectionByPartialName = objConn: Exit Function
        End If
    Next objConn
End Function

' ====================================================================================
' FINGERPRINT (evidencia de mudanca)
' ====================================================================================
Public Function ObterFingerprintTabelaAtiva(Optional ByVal objWsForcado As Worksheet = Nothing) As String
    On Error GoTo Falha
    Dim objWs     As Worksheet
    Dim objLo     As ListObject
    Dim rngDados  As Range
    Dim strBase   As String

    If objWsForcado Is Nothing Then
        Set objWs = ActiveSheet
    Else
        Set objWs = objWsForcado
    End If
    
    If objWs Is Nothing Then Exit Function
    If objWs.ListObjects.count = 0 Then Exit Function
    
    Set objLo = objWs.ListObjects(1)
    If objLo.DataBodyRange Is Nothing Then Exit Function

    Set rngDados = objLo.DataBodyRange
    Dim lngRCount As Long: lngRCount = rngDados.Rows.count
    Dim lngCCount As Long: lngCCount = rngDados.Columns.count
    If lngRCount <= 0 Or lngCCount <= 0 Then Exit Function

    Dim varFirst As Variant: varFirst = rngDados.Cells(1, 1).Value2
    Dim varLast  As Variant: varLast = rngDados.Cells(lngRCount, lngCCount).Value2
    Dim strStampK As String: strStampK = StampKey(GetStampValue())

    strBase = objWs.Name & "|" & objLo.Name & "|" & lngRCount & "x" & lngCCount & "|" & _
              CStr(varFirst) & "|" & CStr(varLast) & "|STAMP:" & strStampK
              
    ObterFingerprintTabelaAtiva = "H=" & GerarHashDJB2(strBase) & "; R=" & lngRCount & "; C=" & lngCCount & "; S=" & strStampK
    Exit Function
    
Falha:
    ObterFingerprintTabelaAtiva = ""
End Function

Private Function GerarHashDJB2(ByVal texto As String) As String
    Dim i As Long
    Dim h As Long
    h = 5381
    For i = 1 To Len(texto)
        h = ((h * 33) Xor AscW(Mid$(texto, i, 1))) And &H7FFFFFFF
    Next i
    GerarHashDJB2 = CStr(h)
End Function
