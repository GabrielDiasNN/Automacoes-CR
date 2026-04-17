Attribute VB_Name = "ClsOutlookAdapter"
VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
End
Option Explicit

Private m_objOutlookApp As Object

Public Function EnviarEmailHtml(ByVal strSubject As String, _
                                ByVal strBodyHtml As String, _
                                ByVal strTo As String, _
                                ByVal strCC As String, _
                                Optional ByVal strAttachmentPath As String = "", _
                                Optional ByVal strIntro As String = "", _
                                Optional ByVal strLegenda As String = "") As Boolean
    Dim objApp As Object
    Dim objItem As Object
    Dim objComposer As ClsEmailComposerService

    On Error GoTo TratarErro

    Set objApp = GetOutlookAppSafe()
    If objApp Is Nothing Then
        GravarLogEx "E-MAIL: Nao foi possivel obter instancia do Outlook.", LOG_ERROR
        EnviarEmailHtml = False
        Exit Function
    End If

    If InStr(1, strTo, "@") = 0 Then
        GravarLogEx "E-MAIL: Destinatario invalido: '" & strTo & "'", LOG_ERROR
        EnviarEmailHtml = False
        Exit Function
    End If

    Set objItem = objApp.CreateItem(0)
    Set objComposer = New ClsEmailComposerService

    With objItem
        .To = strTo
        .CC = strCC
        .Subject = strSubject
        .BodyFormat = 2 ' olFormatHTML
        .htmlBody = objComposer.ComposeHtmlBodyWithSignature(objItem, strIntro, strBodyHtml, strLegenda)

        If Len(strAttachmentPath) > 0 Then
            If TryAddAttachment(objItem, strAttachmentPath) Then
                GravarLogEx "E-MAIL: Anexo adicionado: " & strAttachmentPath, LOG_DEBUG
            Else
                GravarLogEx "E-MAIL: Anexo nao encontrado/invalidado: " & strAttachmentPath, LOG_WARNING
            End If
        End If

        GravarLogEx "E-MAIL: Enviando para [" & strTo & "] | Assunto: [" & strSubject & "]", LOG_INFO
        .Send
    End With

    GravarLogEx "E-MAIL: Enviado com sucesso.", LOG_INFO
    EnviarEmailHtml = True

Saida:
    Set objComposer = Nothing
    Set objItem = Nothing
    Exit Function

TratarErro:
    GravarLogEx "E-MAIL: FALHA: " & Err.Description, LOG_ERROR
    EnviarEmailHtml = False
    Resume Saida
End Function

Public Function GetOutlookAppSafe() As Object
    On Error Resume Next

    If m_objOutlookApp Is Nothing Then
        Set m_objOutlookApp = GetObject(, "Outlook.Application")
    End If

    If m_objOutlookApp Is Nothing Then
        Err.Clear
        Set m_objOutlookApp = CreateObject("Outlook.Application")
    End If

    If m_objOutlookApp Is Nothing Then
        GravarLogEx "OUTLOOK: Falha ao obter instancia. Verifique se o Outlook esta travado.", LOG_ERROR
    Else
        If m_objOutlookApp.Session Is Nothing Then
            m_objOutlookApp.GetNamespace("MAPI").Logon
        End If
    End If

    Set GetOutlookAppSafe = m_objOutlookApp
    On Error GoTo 0
End Function

Public Sub ResetState()
    Set m_objOutlookApp = Nothing
End Sub

Private Function TryAddAttachment(ByVal objItem As Object, ByVal strAttachmentPath As String) As Boolean
    On Error GoTo TratarErro

    If Dir$(strAttachmentPath) = vbNullString Then Exit Function
    If FileLen(strAttachmentPath) <= 0 Then Exit Function

    objItem.Attachments.Add strAttachmentPath
    TryAddAttachment = True
    Exit Function

TratarErro:
    TryAddAttachment = False
End Function
