Attribute VB_Name = "ClsEmailComposerService"
VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
End
Option Explicit

' ==============================================================================
' ClsEmailComposerService  (FONTE CANONICA: _Shared/VBA/)
' Responsabilidade: composicao de corpo HTML para MailItem do Outlook.
' Captura assinatura, injeta intro/legenda e faz encode seguro de texto.
' Sem dependencias externas ao projeto VBA.
' ==============================================================================

Public Function ComposeHtmlBodyWithSignature(ByVal objMailItem As Object, _
                                              ByVal introText As String, _
                                              ByVal bodyHtml As String, _
                                              ByVal legendaHtml As String) As String
    Dim signatureHtml As String
    Dim introMarkup As String
    Dim legendaMarkup As String
    Dim bodyMarkup As String
    Dim contentMarkup As String

    signatureHtml = CaptureOutlookSignatureHtml(objMailItem)
    introMarkup = BuildIntroMarkup(introText)
    legendaMarkup = BuildLegendaMarkup(legendaHtml)
    bodyMarkup = ExtractBodyMarkup(bodyHtml)
    contentMarkup = introMarkup & bodyMarkup & legendaMarkup & BuildSignatureSpacingMarkup()

    ComposeHtmlBodyWithSignature = InjectContentBeforeSignature(signatureHtml, contentMarkup)
End Function

' ------------------------------------------------------------------------------
' PRIVADOS
' ------------------------------------------------------------------------------

Private Function BuildSignatureSpacingMarkup() As String
    BuildSignatureSpacingMarkup = "<p class=MsoNormal><o:p>&nbsp;</o:p></p>"
End Function

Private Function CaptureOutlookSignatureHtml(ByVal objMailItem As Object) As String
    On Error GoTo TratarErro

    objMailItem.Display
    CaptureOutlookSignatureHtml = CStr(objMailItem.htmlBody)
    Exit Function

TratarErro:
    CaptureOutlookSignatureHtml = vbNullString
End Function

Private Function BuildIntroMarkup(ByVal introText As String) As String
    Dim normalized As String

    normalized = Trim$(introText)
    If Len(normalized) = 0 Then
        BuildIntroMarkup = vbNullString
        Exit Function
    End If

    normalized = HtmlEncodeText(normalized)
    normalized = Replace(normalized, vbCrLf, "<br>")
    normalized = Replace(normalized, vbCr, "<br>")
    normalized = Replace(normalized, vbLf, "<br>")

    BuildIntroMarkup = "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' " & _
                       "style='width:100%;margin:0 0 12px 0;border-collapse:collapse;" & _
                       "mso-table-lspace:0pt;mso-table-rspace:0pt;'>" & _
                       "<tr><td style='font-family:Calibri,Arial,sans-serif;font-size:11pt;" & _
                       "color:#1f2937;padding:0;line-height:1.4;'>" & normalized & "</td></tr></table>"
End Function

Private Function BuildLegendaMarkup(ByVal legendaHtml As String) As String
    If Len(Trim$(legendaHtml)) = 0 Then
        BuildLegendaMarkup = vbNullString
        Exit Function
    End If

    BuildLegendaMarkup = "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' " & _
                         "style='width:100%;margin-top:10px;border-collapse:collapse;" & _
                         "mso-table-lspace:0pt;mso-table-rspace:0pt;'>" & _
                         "<tr><td style='padding:7px 10px;border:1px solid #e5e7eb;" & _
                         "background-color:#f8fafc;font-family:Calibri,Arial,sans-serif;" & _
                         "font-size:9pt;color:#667085;line-height:1.35;'>" & legendaHtml & "</td></tr></table>"
End Function

Private Function ExtractBodyMarkup(ByVal bodyHtml As String) As String
    Dim lngBodyOpen   As Long
    Dim lngBodyTagEnd As Long
    Dim lngBodyClose  As Long

    lngBodyOpen = InStr(1, bodyHtml, "<body", vbTextCompare)
    If lngBodyOpen > 0 Then
        lngBodyTagEnd = InStr(lngBodyOpen, bodyHtml, ">", vbBinaryCompare)
        lngBodyClose = InStrRev(bodyHtml, "</body>", -1, vbTextCompare)

        If lngBodyTagEnd > 0 And lngBodyClose > lngBodyTagEnd Then
            ExtractBodyMarkup = Mid$(bodyHtml, lngBodyTagEnd + 1, lngBodyClose - lngBodyTagEnd - 1)
            Exit Function
        End If
    End If

    ExtractBodyMarkup = bodyHtml
End Function

Private Function InjectContentBeforeSignature(ByVal signatureHtml As String, _
                                               ByVal contentMarkup As String) As String
    Dim lngAnchor    As Long
    Dim lngInsertPos As Long
    Dim lngBodyClose As Long
    Dim lngCurrEnd   As Long
    Dim lngPrevStart As Long
    Dim lngPrevEnd   As Long
    Dim strPrevPara  As String
    Dim strBetween   As String

    If Len(signatureHtml) = 0 Then
        InjectContentBeforeSignature = contentMarkup
        Exit Function
    End If

    lngAnchor = InStr(1, signatureHtml, "_MailAutoSig", vbTextCompare)
    If lngAnchor > 0 Then
        lngInsertPos = InStrRev(signatureHtml, "<p", lngAnchor, vbTextCompare)
        If lngInsertPos > 0 Then
            ' Sobe acima de paragrafos vazios consecutivos do Outlook para nao criar gap.
            Do
                lngCurrEnd = InStr(lngInsertPos, signatureHtml, "</p>", vbTextCompare)
                If lngCurrEnd <= 0 Then Exit Do

                lngPrevEnd = InStrRev(signatureHtml, "</p>", lngInsertPos - 1, vbTextCompare)
                If lngPrevEnd <= 0 Then Exit Do

                lngPrevStart = InStrRev(signatureHtml, "<p", lngPrevEnd, vbTextCompare)
                If lngPrevStart <= 0 Then Exit Do

                strBetween = Mid$(signatureHtml, lngPrevEnd + 4, lngInsertPos - lngPrevEnd - 4)
                If Not IsWhitespaceOnly(strBetween) Then Exit Do

                strPrevPara = Mid$(signatureHtml, lngPrevStart, lngPrevEnd - lngPrevStart + 4)
                If IsOutlookEmptyParagraph(strPrevPara) Then
                    lngInsertPos = lngPrevStart
                Else
                    Exit Do
                End If
            Loop

            InjectContentBeforeSignature = Left$(signatureHtml, lngInsertPos - 1) & _
                                           contentMarkup & _
                                           Mid$(signatureHtml, lngInsertPos)
            Exit Function
        End If
    End If

    lngBodyClose = InStrRev(signatureHtml, "</body>", -1, vbTextCompare)
    If lngBodyClose > 0 Then
        InjectContentBeforeSignature = Left$(signatureHtml, lngBodyClose - 1) & _
                                       contentMarkup & _
                                       Mid$(signatureHtml, lngBodyClose)
    Else
        InjectContentBeforeSignature = contentMarkup & signatureHtml
    End If
End Function

Private Function IsWhitespaceOnly(ByVal textValue As String) As Boolean
    Dim normalized As String

    normalized = textValue
    normalized = Replace(normalized, vbCr, vbNullString)
    normalized = Replace(normalized, vbLf, vbNullString)
    normalized = Replace(normalized, vbTab, vbNullString)
    normalized = Replace(normalized, " ", vbNullString)

    IsWhitespaceOnly = (Len(normalized) = 0)
End Function

Private Function IsOutlookEmptyParagraph(ByVal paragraphHtml As String) As Boolean
    Dim normalized As String
    Dim regex      As Object

    normalized = LCase$(paragraphHtml)
    If InStr(1, normalized, "<img", vbTextCompare) > 0 Then
        IsOutlookEmptyParagraph = False
        Exit Function
    End If

    Set regex = CreateObject("VBScript.RegExp")
    regex.Global = True
    regex.IgnoreCase = True
    regex.Pattern = "<[^>]+>"
    normalized = regex.Replace(normalized, vbNullString)

    normalized = Replace(normalized, "&nbsp;", vbNullString)
    normalized = Replace(normalized, "&#160;", vbNullString)
    normalized = Replace(normalized, vbCr, vbNullString)
    normalized = Replace(normalized, vbLf, vbNullString)
    normalized = Replace(normalized, vbTab, vbNullString)
    normalized = Replace(normalized, " ", vbNullString)

    IsOutlookEmptyParagraph = (Len(normalized) = 0)
End Function

Private Function HtmlEncodeText(ByVal textValue As String) As String
    textValue = Replace(textValue, "&", "&amp;")
    textValue = Replace(textValue, "<", "&lt;")
    textValue = Replace(textValue, ">", "&gt;")
    textValue = Replace(textValue, """", "&quot;")
    textValue = Replace(textValue, "'", "&#39;")
    HtmlEncodeText = textValue
End Function
