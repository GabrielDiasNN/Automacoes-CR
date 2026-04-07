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

' ==============================================================================
' ClsRBOutlookAdapter  (wrapper de compatibilidade -> ClsOutlookAdapter)
' Preserva a assinatura publica original (params: sPara, sCopia, sCco, subject, body...).
' Delega para a classe canonica shared reordenando os parametros.
' ==============================================================================

Private m_adapter   As ClsOutlookAdapter
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
    If m_adapter Is Nothing Then Set m_adapter = New ClsOutlookAdapter
    m_lastError = vbNullString

    EnviarEmail = m_adapter.EnviarEmail(strSubject, htmlBody, sPara, sCopia, sCco, strIntro, strLegenda, previewOnly)
    If Not EnviarEmail Then m_lastError = m_adapter.LastError
End Function

Public Sub ResetState()
    If Not m_adapter Is Nothing Then m_adapter.ResetState
    m_lastError = vbNullString
End Sub

Private Sub Class_Terminate()
    Set m_adapter = Nothing
End Sub
