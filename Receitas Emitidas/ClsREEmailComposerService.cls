VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ClsREEmailComposerService"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

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
    contentMarkup = introMarkup & bodyMarkup & legendaMarkup

    ComposeHtmlBodyWithSignature = InjectContentBeforeSignature(signatureHtml, contentMarkup)
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
    Dim normalizedText As String

    normalizedText = Trim$(introText)
    If Len(normalizedText) = 0 Then
        BuildIntroMarkup = vbNullString
        Exit Function
    End If

    normalizedText = HtmlEncodeText(normalizedText)
    normalizedText = Replace(normalizedText, vbCrLf, "<br>")
    normalizedText = Replace(normalizedText, vbCr, "<br>")
    normalizedText = Replace(normalizedText, vbLf, "<br>")

    BuildIntroMarkup = "<p class=MsoNormal>" & normalizedText & "<o:p></o:p></p>"
End Function

Private Function BuildLegendaMarkup(ByVal legendaHtml As String) As String
    If Len(Trim$(legendaHtml)) = 0 Then
        BuildLegendaMarkup = vbNullString
        Exit Function
    End If

    BuildLegendaMarkup = "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;margin-top:10px;border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;'><tr><td style='padding:7px 10px;border:1px solid #e5e7eb;background-color:#f8fafc;font-family:Calibri,Arial,sans-serif;font-size:9pt;color:#667085;line-height:1.35;'>" & legendaHtml & "</td></tr></table>"
End Function

Private Function ExtractBodyMarkup(ByVal bodyHtml As String) As String
    Dim lngBodyOpen As Long
    Dim lngBodyTagEnd As Long
    Dim lngBodyClose As Long

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

Private Function InjectContentBeforeSignature(ByVal signatureHtml As String, ByVal contentMarkup As String) As String
    Dim lngSignatureAnchor As Long
    Dim lngInsertPos As Long
    Dim lngBodyClose As Long

    If Len(signatureHtml) = 0 Then
        InjectContentBeforeSignature = contentMarkup
        Exit Function
    End If

    lngSignatureAnchor = InStr(1, signatureHtml, "_MailAutoSig", vbTextCompare)
    If lngSignatureAnchor > 0 Then
        lngInsertPos = InStrRev(signatureHtml, "<p", lngSignatureAnchor, vbTextCompare)
        If lngInsertPos > 0 Then
            InjectContentBeforeSignature = Left$(signatureHtml, lngInsertPos - 1) & contentMarkup & Mid$(signatureHtml, lngInsertPos)
            Exit Function
        End If
    End If

    lngBodyClose = InStrRev(signatureHtml, "</body>", -1, vbTextCompare)
    If lngBodyClose > 0 Then
        InjectContentBeforeSignature = Left$(signatureHtml, lngBodyClose - 1) & contentMarkup & Mid$(signatureHtml, lngBodyClose)
    Else
        InjectContentBeforeSignature = contentMarkup & signatureHtml
    End If
End Function

Private Function HtmlEncodeText(ByVal textValue As String) As String
    textValue = Replace(textValue, "&", "&amp;")
    textValue = Replace(textValue, "<", "&lt;")
    textValue = Replace(textValue, ">", "&gt;")
    textValue = Replace(textValue, """", "&quot;")
    textValue = Replace(textValue, "'", "&#39;")
    HtmlEncodeText = textValue
End Function
