VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ClsREOutlookAdapter"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Private m_outlookApp As Object
Private m_lastError As String

Public Property Get LastError() As String
    LastError = m_lastError
End Property

Public Function EnviarEmail(ByVal strSubject As String, _
                            ByVal strTo As String, _
                            ByVal strBodyHtml As String, _
                            ByVal strIntro As String, _
                            ByVal strLegenda As String, _
                            ByVal previewOnly As Boolean, _
                            Optional ByVal strAttachmentPath As String = "") As Boolean
    Dim outlookMail As Object
    Dim composer As ClsREEmailComposerService

    On Error GoTo TratarErro
    m_lastError = vbNullString

    If InStr(1, strTo, "@") = 0 Then
        m_lastError = "Destinatario invalido"
        Exit Function
    End If

    Set m_outlookApp = GetOutlookAppSafe()
    If m_outlookApp Is Nothing Then
        m_lastError = "Outlook inacessivel"
        Exit Function
    End If

    Set outlookMail = m_outlookApp.CreateItem(0)
    If outlookMail Is Nothing Then
        m_lastError = "Falha ao criar MailItem"
        Exit Function
    End If

    Set composer = New ClsREEmailComposerService

    With outlookMail
        .Subject = strSubject
        .To = strTo
        .BodyFormat = 2 ' olFormatHTML
        .htmlBody = composer.ComposeHtmlBodyWithSignature(outlookMail, strIntro, strBodyHtml, strLegenda)

        If Len(strAttachmentPath) > 0 Then
            TryAddAttachment outlookMail, strAttachmentPath
        End If

        If previewOnly Then
            .Display
        Else
            .Send
        End If
    End With

    EnviarEmail = True

Saida:
    Set composer = Nothing
    Set outlookMail = Nothing
    Exit Function

TratarErro:
    m_lastError = Err.Description
    EnviarEmail = False
    Resume Saida
End Function

Public Sub ResetState()
    Set m_outlookApp = Nothing
    m_lastError = vbNullString
End Sub

Private Function GetOutlookAppSafe() As Object
    Dim oApp As Object

    On Error Resume Next

    Set oApp = GetObject(, "Outlook.Application")
    If Not oApp Is Nothing Then
        Set GetOutlookAppSafe = oApp
        Exit Function
    End If

    Err.Clear
    Set oApp = CreateObject("Outlook.Application")
    Set GetOutlookAppSafe = oApp
    On Error GoTo 0
End Function

Private Sub TryAddAttachment(ByVal outlookMail As Object, ByVal attachmentPath As String)
    On Error Resume Next

    If Dir$(attachmentPath) = vbNullString Then Exit Sub
    If FileLen(attachmentPath) <= 0 Then Exit Sub

    outlookMail.Attachments.Add attachmentPath
End Sub
