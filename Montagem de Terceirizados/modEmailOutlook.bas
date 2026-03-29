Attribute VB_Name = "modEmailOutlook"
Option Explicit

Public m_objOutlookApp As Object  ' Outlook.Application (late binding)
Private m_strLastEmailKey As String

' ====================================================================================
' RETRY WRAPPERS
' ====================================================================================
Public Sub EnviarEmailComErrosRetry(ByRef udtTel As Telemetria)
    Dim lngTentativa      As Long
    Dim lngDelaySegundos  As Long
    Dim strEmailKey       As String

    strEmailKey = MontarEmailKeyExecucao("ERRO", udtTel)
    If JaNotificacaoEnviada(strEmailKey) Then
        GravarLogEx "Email ERRO ignorado por idempotencia no mesmo run.", LOG_WARNING
        Exit Sub
    End If
    
    For lngTentativa = 1 To MAX_EMAIL_RETRIES
        GravarLogEx "Email ERRO | tentativa " & lngTentativa & "/" & MAX_EMAIL_RETRIES, LOG_INFO
        If EnviarEmailComErros(udtTel) Then
            RegistrarNotificacaoEnviada strEmailKey
            Exit Sub
        End If
        
        If lngTentativa < MAX_EMAIL_RETRIES Then
            lngDelaySegundos = RETRY_DELAY_BASE ^ lngTentativa
            GravarLogEx "Email ERRO falhou. Aguardando " & lngDelaySegundos & "s...", LOG_WARNING
            Application.Wait Now + TimeSerial(0, 0, CInt(lngDelaySegundos))
        End If
    Next lngTentativa
    
    GravarLogEx "FALHA DEFINITIVA: Email ERRO nao enviado.", LOG_ERROR
End Sub

Public Sub EnviarEmailSucessoRetry(ByRef udtTel As Telemetria)
    Dim lngTentativa      As Long
    Dim lngDelaySegundos  As Long
    Dim strEmailKey       As String

    strEmailKey = MontarEmailKeyExecucao("SUCESSO", udtTel)
    If JaNotificacaoEnviada(strEmailKey) Then
        GravarLogEx "Email OK ignorado por idempotencia no mesmo run.", LOG_WARNING
        Exit Sub
    End If
    
    For lngTentativa = 1 To MAX_EMAIL_RETRIES
        GravarLogEx "Email OK | tentativa " & lngTentativa & "/" & MAX_EMAIL_RETRIES, LOG_INFO
        If EnviarEmailSucesso(udtTel) Then
            RegistrarNotificacaoEnviada strEmailKey
            Exit Sub
        End If
        
        If lngTentativa < MAX_EMAIL_RETRIES Then
            lngDelaySegundos = RETRY_DELAY_BASE ^ lngTentativa
            GravarLogEx "Email OK falhou. Aguardando " & lngDelaySegundos & "s...", LOG_WARNING
            Application.Wait Now + TimeSerial(0, 0, CInt(lngDelaySegundos))
        End If
    Next lngTentativa
    
    GravarLogEx "FALHA DEFINITIVA: Email OK nao enviado.", LOG_ERROR
End Sub

Public Sub LimparEstadoNotificacao()
    m_strLastEmailKey = ""
End Sub

' ====================================================================================
' CONSTRUTORES DE EMAIL
' ====================================================================================
Private Function EnviarEmailComErros(ByRef udtTel As Telemetria) As Boolean
    Dim strTo      As String, strCC As String
    Dim strHtml    As String, strAssunto As String

    If Not ObterEValidarDestinatarios(strTo, strCC) Then
        EnviarEmailComErros = False: Exit Function
    End If

    strHtml = MontarTemplateEmail(True, udtTel)
    strAssunto = "[ALERTA] Divergencias - Controle NF - " & FormatarDataBR(Now)
    
    EnviarEmailComErros = EnviarEmailCore(strAssunto, strHtml, strTo, strCC)
End Function

Private Function EnviarEmailSucesso(ByRef udtTel As Telemetria) As Boolean
    Dim strTo      As String, strCC As String
    Dim strHtml    As String, strAssunto As String

    If Not ObterEValidarDestinatarios(strTo, strCC) Then
        EnviarEmailSucesso = False: Exit Function
    End If

    strHtml = MontarTemplateEmail(False, udtTel)
    strAssunto = "[OK] Validacao Aprovada - Controle NF - " & FormatarDataBR(Now)
    
    EnviarEmailSucesso = EnviarEmailCore(strAssunto, strHtml, strTo, strCC)
End Function

' ====================================================================================
' CORE DE ENVIO
' ====================================================================================
Private Function EnviarEmailCore(ByVal strSubject As String, ByVal strBodyHTML As String, _
                                   ByVal strTo As String, ByVal strCC As String, _
                                   Optional ByVal strAttachmentPath As String = "") As Boolean
    Dim objApp  As Object
    Dim objItem As Object
    
    On Error GoTo TratarErro

    Set objApp = GetOutlookAppSafe()
    If objApp Is Nothing Then
        GravarLogEx "E-MAIL: Nao foi possivel obter instancia do Outlook.", LOG_ERROR
        EnviarEmailCore = False: Exit Function
    End If

    If InStr(1, strTo, "@") = 0 Then
        GravarLogEx "E-MAIL: Destinatario invalido: '" & strTo & "'", LOG_ERROR
        EnviarEmailCore = False: Exit Function
    End If

    Set objItem = objApp.CreateItem(0)
    With objItem
        .To = strTo
        .CC = strCC
        .Subject = strSubject
        .BodyFormat = 2 ' olFormatHTML
        .htmlBody = strBodyHTML
        
        If Len(strAttachmentPath) > 0 Then
            If Dir$(strAttachmentPath) <> "" Then
                .Attachments.Add strAttachmentPath
                GravarLogEx "E-MAIL: Anexo adicionado: " & strAttachmentPath, LOG_DEBUG
            Else
                GravarLogEx "E-MAIL: Anexo nao encontrado: " & strAttachmentPath, LOG_WARNING
            End If
        End If
        
        GravarLogEx "E-MAIL: Enviando para [" & strTo & "] | Assunto: [" & strSubject & "]", LOG_INFO
        .Send
    End With

    GravarLogEx "E-MAIL: Enviado com sucesso.", LOG_INFO
    EnviarEmailCore = True
    
Saida:
    Set objItem = Nothing
    Exit Function

TratarErro:
    GravarLogEx "E-MAIL: FALHA: " & Err.Description, LOG_ERROR
    EnviarEmailCore = False
    Resume Saida
End Function

' ====================================================================================
' OUTLOOK INSTANCE (GOVERNANCE SAFE)
' ====================================================================================
Private Function GetOutlookAppSafe() As Object
    On Error Resume Next
    
    ' 1. Tenta conexao com instancia ja aberta (padrao)
    If m_objOutlookApp Is Nothing Then
        Set m_objOutlookApp = GetObject(, "Outlook.Application")
    End If
    
    ' 2. Se nao encontrou, tenta criar nova
    If m_objOutlookApp Is Nothing Then
        Err.Clear
        Set m_objOutlookApp = CreateObject("Outlook.Application")
    End If
    
    ' 3. Se ainda nulo ou sessao invalida, alerta (evita killing agressivo por padrao)
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

' ====================================================================================
' HELPERS
' ====================================================================================
Private Function MontarTemplateEmail(ByVal blnErro As Boolean, ByRef udtTel As Telemetria) As String
    Dim strHtml As String
    Dim strCor  As String
    Dim strIcon As String
    Dim strMsg  As String
    
    If blnErro Then
        strCor = "#d32f2f"
        strIcon = HTML_ICON_WARNING
        strMsg = "Divergencias Detectadas"
    Else
        strCor = "#388e3c"
        strIcon = HTML_ICON_CHECK
        strMsg = "Validacao Aprovada"
    End If

    strHtml = "<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>"
    strHtml = strHtml & "<div style='font-family:Calibri,Arial,sans-serif;font-size:11pt;max-width:800px;margin:0 auto;'>"
    strHtml = strHtml & "<div style='background:linear-gradient(135deg," & strCor & " 0%,#222 100%);padding:20px;border-radius:8px 8px 0 0;'>"
    strHtml = strHtml & "<h1 style='color:white;margin:0;font-size:24pt;'><span style='font-size:32pt;vertical-align:middle;'>" & strIcon & "</span> " & strMsg & "</h1></div>"
    strHtml = strHtml & "<div style='background:#fff;padding:25px;border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px;'>"
    
    If blnErro Then
        strHtml = strHtml & "<p style='font-size:12pt;'><span style='font-size:14pt;'>" & HTML_ICON_MAGNIFY & "</span> <b>Foram detectadas divergencias na validacao.</b></p>"
        strHtml = strHtml & "<p style='font-size:11pt;'><span style='font-size:14pt;'>" & HTML_ICON_PACKAGE & "</span> Consulte a aba <b style='color:#d32f2f;'>Erros NF</b> no Excel.</p>"
    Else
        strHtml = strHtml & "<p style='font-size:12pt;'><span style='font-size:14pt;'>" & HTML_ICON_TROPHY & "</span> <b>Nenhuma divergencia encontrada.</b></p>"
    End If
    
    strHtml = strHtml & "<div style='background:#f9f9f9;border-left:4px solid " & strCor & ";padding:15px;margin:20px 0;border-radius:4px;'>"
    strHtml = strHtml & "<p><span style='font-size:14pt;'>" & HTML_ICON_CHART & "</span> <b>Total de linhas:</b> " & udtTel.totalLinhas & "</p>"
    strHtml = strHtml & "<p><span style='font-size:14pt;'>" & IIf(blnErro, HTML_ICON_CROSS, HTML_ICON_CHECK) & "</span> <b>Resultado:</b> " & IIf(blnErro, udtTel.totalErros & " erros", "100% OK") & "</p>"
    strHtml = strHtml & "<p><span style='font-size:14pt;'>" & HTML_ICON_STOPWATCH & "</span> <b>Tempo de Processamento:</b> " & Format$(TimerElapsed(udtTel.InicioExecucao), "0.00") & "s</p></div>"
    
    strHtml = strHtml & "<hr style='border:0;border-top:1px solid #ddd;margin:30px 0;'>"
    strHtml = strHtml & "<p style='font-size:9pt;color:#888;'><span style='font-size:12pt;'>" & HTML_ICON_ROBOT & "</span> <i>Robo Fiscal " & ROBO_VERSAO_DASH & "</i><br>"
    strHtml = strHtml & "<span style='font-size:12pt;'>" & HTML_ICON_CALENDAR & "</span> Data/Hora: <b>" & FormatarDataBR(Now, True) & "</b></p>"
    strHtml = strHtml & "</div></div></body></html>"
    
    MontarTemplateEmail = strHtml
End Function

Private Function MontarEmailKeyExecucao(ByVal strTipo As String, ByRef udtTel As Telemetria) As String
    MontarEmailKeyExecucao = strTipo & "|" & GetRunId() & "|" & CStr(udtTel.totalLinhas) & "|" & CStr(udtTel.totalErros)
End Function

Private Function JaNotificacaoEnviada(ByVal strEmailKey As String) As Boolean
    JaNotificacaoEnviada = (Len(m_strLastEmailKey) > 0 And StrComp(m_strLastEmailKey, strEmailKey, vbBinaryCompare) = 0)
End Function

Private Sub RegistrarNotificacaoEnviada(ByVal strEmailKey As String)
    m_strLastEmailKey = strEmailKey
End Sub

Public Function ObterEValidarDestinatarios(ByRef strTo As String, ByRef strCC As String) As Boolean
    Const TO_PADRAO As String = "email1@empresa.com.br;email2@empresa.com.br"
    Const CC_PADRAO As String = "email3@empresa.com.br;email4@empresa.com.br"

    Dim objWs      As Worksheet
    Dim objTbl     As ListObject
    Dim strTempTo  As String
    Dim strTempCC  As String
    Dim blnLeuConfig As Boolean

    On Error Resume Next
    Set objWs = ThisWorkbook.Worksheets("Config")
    If Not objWs Is Nothing Then
        Set objTbl = objWs.ListObjects("EnderecosEmail")
        If Not objTbl Is Nothing Then
            strTempTo = CStr(objTbl.ListColumns("Para").DataBodyRange.Cells(1, 1).Value)
            strTempCC = CStr(objTbl.ListColumns("Copia").DataBodyRange.Cells(1, 1).Value)
            blnLeuConfig = (Err.Number = 0)
        End If
    End If
    On Error GoTo 0

    strTo = IIf(blnLeuConfig And Len(Trim$(strTempTo)) > 0, Replace(Trim$(strTempTo), " ", ""), TO_PADRAO)
    strCC = IIf(blnLeuConfig And Len(Trim$(strTempCC)) > 0, Replace(Trim$(strTempCC), " ", ""), CC_PADRAO)

    ObterEValidarDestinatarios = (InStr(1, strTo, "@") > 0)
End Function
