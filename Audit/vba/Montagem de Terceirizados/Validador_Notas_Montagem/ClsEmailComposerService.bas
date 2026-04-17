Attribute VB_Name = "ClsEmailComposerService"
VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
End
Option Explicit

Public Function ComposeHtmlBodyWithSignature(ByVal objItem As Object, _
                                             ByVal strIntro As String, _
                                             ByVal strBodyHtml As String, _
                                             ByVal strLegenda As String) As String
    Dim strSignatureHtml As String
    Dim strIntroMarkup As String
    Dim strLegendaMarkup As String
    Dim strBodyComBlocos As String

    strSignatureHtml = CaptureOutlookSignatureHtml(objItem)
    strIntroMarkup = BuildIntroMarkup(strIntro)
    strLegendaMarkup = BuildLegendaMarkup(strLegenda)
    strBodyComBlocos = InjectIntroAndLegenda(strBodyHtml, strIntroMarkup, strLegendaMarkup)

    ComposeHtmlBodyWithSignature = strBodyComBlocos & strSignatureHtml
End Function

Private Function CaptureOutlookSignatureHtml(ByVal objItem As Object) As String
    On Error GoTo TratarErro

    objItem.Display
    CaptureOutlookSignatureHtml = CStr(objItem.htmlBody)
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

    BuildIntroMarkup = "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;margin:0 0 12px 0;border-collapse:collapse;'><tr><td style='font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#1f2937;padding:0;line-height:1.4;'>" & strSafe & "</td></tr></table>"
End Function

Private Function BuildLegendaMarkup(ByVal strLegenda As String) As String
    If Len(Trim$(strLegenda)) = 0 Then
        BuildLegendaMarkup = vbNullString
        Exit Function
    End If

    BuildLegendaMarkup = "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;margin-top:14px;border-collapse:collapse;'><tr><td style='padding:10px;border-left:4px solid #f39c12;background-color:#f8f9f9;font-family:Calibri,Arial,sans-serif;font-size:10pt;color:#333333;'>" & strLegenda & "</td></tr></table>"
End Function

Private Function InjectIntroAndLegenda(ByVal strBodyHtml As String, _
                                       ByVal strIntroMarkup As String, _
                                       ByVal strLegendaMarkup As String) As String
    Dim lngBodyOpen As Long
    Dim lngBodyTagEnd As Long
    Dim lngBodyClose As Long
    Dim strBefore As String
    Dim strInside As String
    Dim strAfter As String

    lngBodyOpen = InStr(1, strBodyHtml, "<body", vbTextCompare)

    If lngBodyOpen > 0 Then
        lngBodyTagEnd = InStr(lngBodyOpen, strBodyHtml, ">", vbBinaryCompare)
        lngBodyClose = InStrRev(strBodyHtml, "</body>", -1, vbTextCompare)

        If lngBodyTagEnd > 0 And lngBodyClose > lngBodyTagEnd Then
            strBefore = Left$(strBodyHtml, lngBodyTagEnd)
            strInside = Mid$(strBodyHtml, lngBodyTagEnd + 1, lngBodyClose - lngBodyTagEnd - 1)
            strAfter = Mid$(strBodyHtml, lngBodyClose)

            InjectIntroAndLegenda = strBefore & strIntroMarkup & strInside & strLegendaMarkup & strAfter
            Exit Function
        End If
    End If

    InjectIntroAndLegenda = strIntroMarkup & strBodyHtml & strLegendaMarkup
End Function

Private Function HtmlEncodeText(ByVal strValue As String) As String
    strValue = Replace(strValue, "&", "&amp;")
    strValue = Replace(strValue, "<", "&lt;")
    strValue = Replace(strValue, ">", "&gt;")
    strValue = Replace(strValue, """", "&quot;")
    strValue = Replace(strValue, "'", "&#39;")
    HtmlEncodeText = strValue
End Function
