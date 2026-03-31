VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ClsRBEmailComposerService"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Public Function ComposeHtmlBodyWithSignature(ByVal email As Object, _
                                             ByVal strIntro As String, _
                                             ByVal htmlBody As String, _
                                             ByVal strLegenda As String) As String
    Dim strSignatureHtml As String
    Dim strIntroMarkup As String
    Dim strLegendaMarkup As String
    Dim strBodyMarkup As String
    Dim strContentMarkup As String

    strSignatureHtml = CaptureOutlookSignatureHtml(email)
    strIntroMarkup = BuildIntroMarkup(strIntro)
    strLegendaMarkup = BuildLegendaMarkup(strLegenda)
    strBodyMarkup = ExtractBodyMarkup(htmlBody)
    strContentMarkup = strIntroMarkup & strBodyMarkup & strLegendaMarkup

    ComposeHtmlBodyWithSignature = InjectContentBeforeSignature(strSignatureHtml, strContentMarkup)
End Function

Private Function CaptureOutlookSignatureHtml(ByVal email As Object) As String
    On Error GoTo TratarErro

    email.Display
    CaptureOutlookSignatureHtml = CStr(email.htmlBody)
    Exit Function

TratarErro:
    CaptureOutlookSignatureHtml = vbNullString
End Function

Private Function BuildIntroMarkup(ByVal strIntro As String) As String
    Dim strSafe As String

    strSafe = Trim$(strIntro)
    If Len(strSafe) = 0 Then
        BuildIntroMarkup = vbNullString
        Exit Function
    End If

    strSafe = HtmlEncodeText(strSafe)
    strSafe = Replace(strSafe, vbCrLf, "<br>")
    strSafe = Replace(strSafe, vbCr, "<br>")
    strSafe = Replace(strSafe, vbLf, "<br>")

    BuildIntroMarkup = "<p class=MsoNormal>" & strSafe & "<o:p></o:p></p>"
End Function

Private Function BuildLegendaMarkup(ByVal strLegenda As String) As String
    If Len(Trim$(strLegenda)) = 0 Then
        BuildLegendaMarkup = vbNullString
        Exit Function
    End If

    BuildLegendaMarkup = "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;margin-top:10px;border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;'><tr><td style='padding:7px 10px;border:1px solid #e5e7eb;background-color:#f8fafc;font-family:Calibri,Arial,sans-serif;font-size:9pt;color:#667085;line-height:1.35;'>" & strLegenda & "</td></tr></table>"
End Function

Private Function ExtractBodyMarkup(ByVal htmlBody As String) As String
    Dim lngBodyOpen As Long
    Dim lngBodyTagEnd As Long
    Dim lngBodyClose As Long

    lngBodyOpen = InStr(1, htmlBody, "<body", vbTextCompare)
    If lngBodyOpen > 0 Then
        lngBodyTagEnd = InStr(lngBodyOpen, htmlBody, ">", vbBinaryCompare)
        lngBodyClose = InStrRev(htmlBody, "</body>", -1, vbTextCompare)

        If lngBodyTagEnd > 0 And lngBodyClose > lngBodyTagEnd Then
            ExtractBodyMarkup = Mid$(htmlBody, lngBodyTagEnd + 1, lngBodyClose - lngBodyTagEnd - 1)
            Exit Function
        End If
    End If

    ExtractBodyMarkup = htmlBody
End Function

Private Function InjectContentBeforeSignature(ByVal strSignatureHtml As String, ByVal strContentMarkup As String) As String
    Dim lngSignatureAnchor As Long
    Dim lngInsertPos As Long
    Dim lngBodyClose As Long

    If Len(strSignatureHtml) = 0 Then
        InjectContentBeforeSignature = strContentMarkup
        Exit Function
    End If

    lngSignatureAnchor = InStr(1, strSignatureHtml, "_MailAutoSig", vbTextCompare)
    If lngSignatureAnchor > 0 Then
        lngInsertPos = InStrRev(strSignatureHtml, "<p", lngSignatureAnchor, vbTextCompare)
        If lngInsertPos > 0 Then
            InjectContentBeforeSignature = Left$(strSignatureHtml, lngInsertPos - 1) & strContentMarkup & Mid$(strSignatureHtml, lngInsertPos)
            Exit Function
        End If
    End If

    lngBodyClose = InStrRev(strSignatureHtml, "</body>", -1, vbTextCompare)
    If lngBodyClose > 0 Then
        InjectContentBeforeSignature = Left$(strSignatureHtml, lngBodyClose - 1) & strContentMarkup & Mid$(strSignatureHtml, lngBodyClose)
    Else
        InjectContentBeforeSignature = strContentMarkup & strSignatureHtml
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
