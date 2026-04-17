Attribute VB_Name = "ClsRBEmailComposerService"
VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
End
Option Explicit

' ==============================================================================
' ClsRBEmailComposerService  (wrapper de compatibilidade -> ClsEmailComposerService)
' Preserva a assinatura publica original; delega para a classe canonica shared.
' ==============================================================================

Private m_composer As ClsEmailComposerService

Public Function ComposeHtmlBodyWithSignature(ByVal email As Object, _
                                             ByVal strIntro As String, _
                                             ByVal htmlBody As String, _
                                             ByVal strLegenda As String) As String
    If m_composer Is Nothing Then Set m_composer = New ClsEmailComposerService
    ComposeHtmlBodyWithSignature = m_composer.ComposeHtmlBodyWithSignature(email, strIntro, htmlBody, strLegenda)
End Function

Private Sub Class_Terminate()
    Set m_composer = Nothing
End Sub

Private Function BuildSignatureSpacingMarkup() As String
    BuildSignatureSpacingMarkup = "<p class=MsoNormal><o:p>&nbsp;</o:p></p>"
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

    BuildIntroMarkup = "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;margin:0 0 12px 0;border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;'><tr><td style='font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#1f2937;padding:0;line-height:1.4;'>" & strSafe & "</td></tr></table>"
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
    Dim lngCurrentEnd As Long
    Dim lngPrevStart As Long
    Dim lngPrevEnd As Long
    Dim strPrevParagraph As String
    Dim strBetween As String

    If Len(strSignatureHtml) = 0 Then
        InjectContentBeforeSignature = strContentMarkup
        Exit Function
    End If

    lngSignatureAnchor = InStr(1, strSignatureHtml, "_MailAutoSig", vbTextCompare)
    If lngSignatureAnchor > 0 Then
        lngInsertPos = InStrRev(strSignatureHtml, "<p", lngSignatureAnchor, vbTextCompare)
        If lngInsertPos > 0 Then
            ' Move insertion point above consecutive empty Outlook paragraphs so they stay
            ' as spacing before signature instead of creating a gap before the intro.
            Do
                lngCurrentEnd = InStr(lngInsertPos, strSignatureHtml, "</p>", vbTextCompare)
                If lngCurrentEnd <= 0 Then Exit Do

                lngPrevEnd = InStrRev(strSignatureHtml, "</p>", lngInsertPos - 1, vbTextCompare)
                If lngPrevEnd <= 0 Then Exit Do

                lngPrevStart = InStrRev(strSignatureHtml, "<p", lngPrevEnd, vbTextCompare)
                If lngPrevStart <= 0 Then Exit Do

                strBetween = Mid$(strSignatureHtml, lngPrevEnd + 4, lngInsertPos - lngPrevEnd - 4)
                If Not IsWhitespaceOnly(strBetween) Then Exit Do

                strPrevParagraph = Mid$(strSignatureHtml, lngPrevStart, lngPrevEnd - lngPrevStart + 4)
                If IsOutlookEmptyParagraph(strPrevParagraph) Then
                    lngInsertPos = lngPrevStart
                Else
                    Exit Do
                End If
            Loop

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

Private Function IsWhitespaceOnly(ByVal strTextValue As String) As Boolean
    Dim strNormalized As String

    strNormalized = strTextValue
    strNormalized = Replace(strNormalized, vbCr, vbNullString)
    strNormalized = Replace(strNormalized, vbLf, vbNullString)
    strNormalized = Replace(strNormalized, vbTab, vbNullString)
    strNormalized = Replace(strNormalized, " ", vbNullString)

    IsWhitespaceOnly = (Len(strNormalized) = 0)
End Function

Private Function IsOutlookEmptyParagraph(ByVal strParagraphHtml As String) As Boolean
    Dim strNormalized As String
    Dim regex As Object

    strNormalized = LCase$(strParagraphHtml)
    If InStr(1, strNormalized, "<img", vbTextCompare) > 0 Then
        IsOutlookEmptyParagraph = False
        Exit Function
    End If

    Set regex = CreateObject("VBScript.RegExp")
    regex.Global = True
    regex.IgnoreCase = True
    regex.Pattern = "<[^>]+>"
    strNormalized = regex.Replace(strNormalized, vbNullString)

    strNormalized = Replace(strNormalized, "&nbsp;", vbNullString)
    strNormalized = Replace(strNormalized, "&#160;", vbNullString)
    strNormalized = Replace(strNormalized, vbCr, vbNullString)
    strNormalized = Replace(strNormalized, vbLf, vbNullString)
    strNormalized = Replace(strNormalized, vbTab, vbNullString)
    strNormalized = Replace(strNormalized, " ", vbNullString)

    IsOutlookEmptyParagraph = (Len(strNormalized) = 0)
End Function

Private Function HtmlEncodeText(ByVal textValue As String) As String
    textValue = Replace(textValue, "&", "&amp;")
    textValue = Replace(textValue, "<", "&lt;")
    textValue = Replace(textValue, ">", "&gt;")
    textValue = Replace(textValue, """", "&quot;")
    textValue = Replace(textValue, "'", "&#39;")
    HtmlEncodeText = textValue
End Function
