VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ClsOutlookAdapter"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

' {
'   "version": "1.2.0",
'   "skill": "ai-native-development-standard, automacao-comms-email",
'   "description": "COM Adapter for robust Outlook email dispatch with test redirection support.",
'   "context": "Shared Infrastructure"
' }

' ==============================================================================
' ClsOutlookAdapter  (FONTE CANONICA: _Shared/VBA/)
' Responsabilidade: interface com Outlook para envio de emails HTML.
' Sem dependencias externas: erros sao expostos via LastError.
' O caller e responsavel por logar LastError apos cada chamada.
' ==============================================================================

Private m_oApp              As Object
Private m_lastError         As String
Private m_bWeStartedOutlook As Boolean

Public Property Get LastError() As String
    LastError = m_lastError
End Property

' strPara    : destinatario principal (obrigatorio; deve conter "@")
' strCopia   : CC (opcional)
' strCco     : BCC (opcional)
' strIntro   : texto de introducao antes do corpo (opcional)
' strLegenda : rodape/legenda abaixo do corpo (opcional)
' bPreviewOnly: True exibe o email sem enviar
' strAttachmentPath: caminho completo do arquivo a anexar (opcional)
Public Function EnviarEmail(ByVal strSubject As String, _
                             ByVal strBodyHtml As String, _
                             ByVal strPara As String, _
                             Optional ByVal strCopia As String = "", _
                             Optional ByVal strCco As String = "", _
                             Optional ByVal strIntro As String = "", _
                             Optional ByVal strLegenda As String = "", _
                             Optional ByVal bPreviewOnly As Boolean = False, _
                             Optional ByVal strAttachmentPath As String = "") As Boolean
    Dim oApp     As Object
    Dim oItem    As Object
    Dim composer As ClsEmailComposerService

    On Error GoTo TratarErro

    m_lastError = vbNullString

    If InStr(1, strPara, "@") = 0 Then
        m_lastError = "Destinatario invalido: " & strPara
        Exit Function
    End If

    Set oApp = GetOutlookAppSafe()
    If oApp Is Nothing Then
        m_lastError = "Outlook inacessivel"
        Exit Function
    End If

    Set oItem = oApp.CreateItem(0)
    If oItem Is Nothing Then
        m_lastError = "Falha ao criar MailItem"
        Exit Function
    End If

    Set composer = New ClsEmailComposerService

    ' Redirecionamento para testes (Se AUTOMACAO_TEST_EMAIL estiver definida no ambiente)
    Dim strTestEmail As String
    strTestEmail = Environ$("AUTOMACAO_TEST_EMAIL")
    If Len(strTestEmail) > 0 Then
        ' modLogging.bas deve estar disponivel no projeto para registrar o redirecionamento
        On Error Resume Next
        LogMensagem "MODO TESTE ATIVO: Redirecionando e-mail de " & strPara & " para " & strTestEmail, "WARN"
        On Error GoTo TratarErro
        
        strPara = strTestEmail
        strCopia = ""
        strCco = ""
        strSubject = "[TESTE] " & strSubject
    End If

    With oItem
        .Subject = strSubject
        .To = strPara
        If Len(strCopia) > 0 Then .CC = strCopia
        If Len(strCco) > 0 Then .BCC = strCco
        .BodyFormat = 2  ' olFormatHTML
        .htmlBody = composer.ComposeHtmlBodyWithSignature(oItem, strIntro, strBodyHtml, strLegenda)

        If Len(strAttachmentPath) > 0 Then
            TryAddAttachment oItem, strAttachmentPath
        End If

        If bPreviewOnly Then
            .Display
        Else
            .Send
        End If
    End With

    EnviarEmail = True

Saida:
    Set composer = Nothing
    Set oItem = Nothing
    
    ' Estrategia de Liberacao: Apenas limpa a variavel de memoria, NAO executa .Quit()
    ' para garantir que os e-mails tenham tempo de sair da Caixa de Saida (Outbox).
    Set m_oApp = Nothing
    
    Exit Function

TratarErro:
    If Len(m_lastError) = 0 Then m_lastError = Err.Description
    EnviarEmail = False
    Resume Saida
End Function

' Compatibilidade retroativa para fluxos antigos da Montagem que
' ainda chamam EnviarEmailHtml com assinatura reduzida.
Public Function EnviarEmailHtml(ByVal strSubject As String, _
                                ByVal strBodyHtml As String, _
                                ByVal strTo As String, _
                                ByVal strCC As String, _
                                Optional ByVal strAttachmentPath As String = "", _
                                Optional ByVal strIntro As String = "", _
                                Optional ByVal strLegenda As String = "") As Boolean
    EnviarEmailHtml = EnviarEmail(strSubject, strBodyHtml, strTo, strCC, "", strIntro, strLegenda, False, strAttachmentPath)
End Function

Public Function GetOutlookAppSafe() As Object
    On Error Resume Next

    If m_oApp Is Nothing Then
        Set m_oApp = GetObject(, "Outlook.Application")
        m_bWeStartedOutlook = False
    End If

    If m_oApp Is Nothing Then
        Err.Clear
        Set m_oApp = CreateObject("Outlook.Application")
        m_bWeStartedOutlook = True
    End If

    If Not m_oApp Is Nothing Then
        If m_oApp.Session Is Nothing Then
            m_oApp.GetNamespace("MAPI").Logon
        End If
    End If

    Set GetOutlookAppSafe = m_oApp
    On Error GoTo 0
End Function

Public Sub ResetState()
    Set m_oApp = Nothing
    m_lastError = vbNullString
End Sub

Private Sub TryAddAttachment(ByVal oItem As Object, ByVal strAttachmentPath As String)
    On Error Resume Next

    If Dir$(strAttachmentPath) = vbNullString Then Exit Sub
    If FileLen(strAttachmentPath) <= 0 Then Exit Sub

    oItem.Attachments.Add strAttachmentPath
End Sub
