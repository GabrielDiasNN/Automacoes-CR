VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ClsRBOutlookAdapter"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Private m_oApp As Object
Private m_lastError As String

Public Property Get LastError() As String
    LastError = m_lastError
End Property

Public Function EnviarEmail(ByVal sPara As String, _
                            ByVal sCopia As String, _
                            ByVal sCco As String, _
                            ByVal strSubject As String, _
                            ByVal htmlBody As String, _
                            ByVal strIntro As String, _
                            ByVal strLegenda As String, _
                            Optional ByVal previewOnly As Boolean = False) As Boolean
    Dim email As Object
    Dim composer As ClsRBEmailComposerService
    Dim sendErr As Long
    Dim sendDesc As String

    On Error GoTo TratarErro
    m_lastError = vbNullString

    Set m_oApp = PrepararOutlookComForcaBruta()
    If m_oApp Is Nothing Then
        m_lastError = "Outlook inacessivel"
        Exit Function
    End If

    Set email = m_oApp.CreateItem(0)
    If email Is Nothing Then
        m_lastError = "Falha ao criar MailItem"
        Exit Function
    End If

    Set composer = New ClsRBEmailComposerService

    With email
        .To = sPara
        If Len(sCopia) > 0 Then .CC = sCopia
        If Len(sCco) > 0 Then .BCC = sCco
        .Subject = strSubject
        .htmlBody = composer.ComposeHtmlBodyWithSignature(email, strIntro, htmlBody, strLegenda)
        On Error Resume Next
        If previewOnly Then
            .Display
        Else
            .Send
        End If
        sendErr = Err.Number
        sendDesc = Err.Description
        On Error GoTo TratarErro
        If sendErr <> 0 Then
            m_lastError = sendDesc
            Err.Raise sendErr, "ClsRBOutlookAdapter.Send", sendDesc
        End If
    End With

    EnviarEmail = True

Saida:
    Set composer = Nothing
    Set email = Nothing
    Exit Function

TratarErro:
    If Len(m_lastError) = 0 Then m_lastError = Err.Description
    EnviarEmail = False
    Resume Saida
End Function

Public Sub ResetState()
    Set m_oApp = Nothing
    m_lastError = vbNullString
End Sub

Private Function PrepararOutlookComForcaBruta() As Object
    Dim oApp As Object

    On Error Resume Next

    Set oApp = GetObject(, "Outlook.Application")
    If Not oApp Is Nothing Then
        Set PrepararOutlookComForcaBruta = oApp
        Exit Function
    End If

    Err.Clear
    Set oApp = CreateObject("Outlook.Application")
    Set PrepararOutlookComForcaBruta = oApp
    On Error GoTo 0
End Function
