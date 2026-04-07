Attribute VB_Name = "modEmailOutlook"
Option Explicit

Private m_objOutlookAdapter As ClsOutlookAdapter
Private m_strLastEmailKey   As String
Private m_arrUltimosErros() As DadosErro   ' Staged via PrepararErrosParaEmail
Private m_lngUltimosErrosCount As Long     ' 0 = nenhum erro em staging

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
    m_lngUltimosErrosCount = 0
    If Not m_objOutlookAdapter Is Nothing Then
        m_objOutlookAdapter.ResetState
    End If
End Sub

' Staging de erros para incluir na tabela HTML do email de alerta.
' Deve ser chamado em modNotificacaoNF antes de EnviarEmailComErrosRetry.
Public Sub PrepararErrosParaEmail(ByRef arrErros() As DadosErro, ByVal lngQtd As Long)
    Dim lngI As Long
    m_lngUltimosErrosCount = 0
    If lngQtd < 1 Then Exit Sub
    On Error Resume Next
    ReDim m_arrUltimosErros(1 To lngQtd)
    For lngI = 1 To lngQtd
        m_arrUltimosErros(lngI) = arrErros(lngI)
    Next lngI
    If Err.Number = 0 Then m_lngUltimosErrosCount = lngQtd
    On Error GoTo 0
    GravarLogEx "PrepararErrosParaEmail: " & m_lngUltimosErrosCount & " erros em staging.", LOG_DEBUG
End Sub

' ====================================================================================
' SMOKE TEST (USE NO VBE PARA VALIDAR ENVIO ISOLADO SEM PASSAR PELO PLUGIN)
' ====================================================================================
Public Sub TestarEnvioEmail()
    ' Executa um envio de e-mail de erro direto, sem acionar o plugin de delta.
    ' Util para verificar se o Outlook esta configurado e os destinatarios corretos.
    Dim udtTelTeste As Telemetria

    LimparEstadoNotificacao

    With udtTelTeste
        .InicioExecucao = Timer
        .totalLinhas = 84
        .totalErros = 3
    End With

    GravarLogEx "[SMOKE TEST] Iniciando test de envio direto de e-mail de erro...", LOG_INFO
    EnviarEmailComErrosRetry udtTelTeste
    GravarLogEx "[SMOKE TEST] Concluido.", LOG_INFO

    MsgBox "Smoke test concluido. Verifique o log e o Outlook.", vbInformation, "TestarEnvioEmail"
End Sub

' ====================================================================================
' CONSTRUTORES DE EMAIL
' ====================================================================================
Private Function EnviarEmailComErros(ByRef udtTel As Telemetria) As Boolean
    Dim strTo      As String, strCC As String
    Dim strHtml    As String, strAssunto As String
    Dim strIntro   As String
    Dim strLegenda As String

    If Not ObterEValidarDestinatarios(strTo, strCC) Then
        EnviarEmailComErros = False: Exit Function
    End If

    strIntro = "Segue relat" & ChrW$(243) & "rio automatizado da valida" & ChrW$(231) & "" & ChrW$(227) & "o de notas fiscais."
    strLegenda = "<span style='color:#b91c1c;font-weight:bold;'>Aten&ccedil;&atilde;o: diverg&ecirc;ncias detectadas. Consulte a aba Erros NF para tratar os itens.</span>"
    strHtml = MontarTemplateEmail(True, udtTel)
    strAssunto = "[ALERTA] Diverg" & ChrW$(234) & "ncias - Controle NF - " & FormatarDataBR(Now)

    EnviarEmailComErros = EnviarEmailCore(strAssunto, strHtml, strTo, strCC, "", strIntro, strLegenda)
End Function

Private Function EnviarEmailSucesso(ByRef udtTel As Telemetria) As Boolean
    Dim strTo      As String, strCC As String
    Dim strHtml    As String, strAssunto As String
    Dim strIntro   As String
    Dim strLegenda As String

    If Not ObterEValidarDestinatarios(strTo, strCC) Then
        EnviarEmailSucesso = False: Exit Function
    End If

    strIntro = "Segue relat" & ChrW$(243) & "rio automatizado da valida" & ChrW$(231) & "" & ChrW$(227) & "o de notas fiscais."
    strLegenda = vbNullString
    strHtml = MontarTemplateEmail(False, udtTel)
    strAssunto = "[OK] Valida" & ChrW$(231) & "" & ChrW$(227) & "o Aprovada - Controle NF - " & FormatarDataBR(Now)

    EnviarEmailSucesso = EnviarEmailCore(strAssunto, strHtml, strTo, strCC, "", strIntro, strLegenda)
End Function

' ====================================================================================
' CORE DE ENVIO
' ====================================================================================
Private Function EnviarEmailCore(ByVal strSubject As String, ByVal strBodyHtml As String, _
                                   ByVal strTo As String, ByVal strCC As String, _
                                   Optional ByVal strAttachmentPath As String = "", _
                                   Optional ByVal strIntro As String = "", _
                                   Optional ByVal strLegenda As String = "") As Boolean
    Dim objAdapter As ClsOutlookAdapter

    On Error GoTo TratarErro

    Set objAdapter = GetOutlookAdapter()
    GravarLogEx "E-MAIL: Enviando para [" & strTo & "] | Assunto: [" & strSubject & "]", LOG_INFO
    EnviarEmailCore = objAdapter.EnviarEmail(strSubject, strBodyHtml, strTo, strCC, vbNullString, strIntro, strLegenda, False, strAttachmentPath)
    If EnviarEmailCore Then
        GravarLogEx "E-MAIL: Enviado com sucesso.", LOG_INFO
    Else
        GravarLogEx "E-MAIL: FALHA: " & objAdapter.LastError, LOG_ERROR
    End If

Saida:
    Set objAdapter = Nothing
    Exit Function

TratarErro:
    GravarLogEx "E-MAIL: FALHA: " & Err.Description, LOG_ERROR
    EnviarEmailCore = False
    Resume Saida
End Function

' ====================================================================================
' OUTLOOK INSTANCE (GOVERNANCE SAFE)
' ====================================================================================
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
        strMsg = "Diverg&ecirc;ncias Detectadas"
    Else
        strCor = "#388e3c"
        strIcon = HTML_ICON_CHECK
        strMsg = "Valida&ccedil;&atilde;o Aprovada"
    End If

    strHtml = "<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>"
    strHtml = strHtml & "<div style='font-family:Calibri,Arial,sans-serif;font-size:11pt;max-width:800px;margin:0 auto;'>"
    strHtml = strHtml & "<div style='background:linear-gradient(135deg," & strCor & " 0%,#222 100%);padding:20px;border-radius:8px 8px 0 0;'>"
    strHtml = strHtml & "<h1 style='color:white;margin:0;font-size:24pt;'><span style='font-size:32pt;vertical-align:middle;'>" & strIcon & "</span> " & strMsg & "</h1></div>"
    strHtml = strHtml & "<div style='background:#fff;padding:25px;border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px;'>"

    If blnErro Then
        strHtml = strHtml & "<p style='font-size:12pt;'><span style='font-size:14pt;'>" & HTML_ICON_MAGNIFY & "</span> <b>Foram detectadas diverg&ecirc;ncias na valida&ccedil;&atilde;o.</b></p>"
        strHtml = strHtml & "<p style='font-size:11pt;'><span style='font-size:14pt;'>" & HTML_ICON_PACKAGE & "</span> Consulte a aba <b style='color:#d32f2f;'>Erros NF</b> no Excel.</p>"
        ' Tabela de erros (disponivel se PrepararErrosParaEmail foi chamado antes)
        If m_lngUltimosErrosCount > 0 Then
            strHtml = strHtml & GerarTabelaErrosHtml(m_arrUltimosErros, m_lngUltimosErrosCount)
        End If
    Else
        strHtml = strHtml & "<p style='font-size:12pt;'><span style='font-size:14pt;'>" & HTML_ICON_TROPHY & "</span> <b>Nenhuma diverg&ecirc;ncia encontrada.</b></p>"
    End If

    strHtml = strHtml & "<div style='background:#f9f9f9;border-left:4px solid " & strCor & ";padding:15px;margin:20px 0;border-radius:4px;'>"
    strHtml = strHtml & "<p><span style='font-size:14pt;'>" & HTML_ICON_CHART & "</span> <b>Total de linhas:</b> " & udtTel.totalLinhas & "</p>"
    strHtml = strHtml & "<p><span style='font-size:14pt;'>" & IIf(blnErro, HTML_ICON_CROSS, HTML_ICON_CHECK) & "</span> <b>Resultado:</b> " & IIf(blnErro, udtTel.totalErros & " erros", "100% OK") & "</p>"
    strHtml = strHtml & "<p><span style='font-size:14pt;'>" & HTML_ICON_STOPWATCH & "</span> <b>Tempo de Processamento:</b> " & Format$(TimerElapsed(udtTel.InicioExecucao), "0.00") & "s</p></div>"

    strHtml = strHtml & "<hr style='border:0;border-top:1px solid #ddd;margin:30px 0;'>"
    strHtml = strHtml & "<p style='font-size:9pt;color:#888;'><span style='font-size:12pt;'>" & HTML_ICON_ROBOT & "</span> <i>Rob" & ChrW$(244) & " Fiscal " & ROBO_VERSAO_DASH & "</i><br>"
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

Private Function GetOutlookAdapter() As ClsOutlookAdapter
    If m_objOutlookAdapter Is Nothing Then
        Set m_objOutlookAdapter = New ClsOutlookAdapter
    End If

    Set GetOutlookAdapter = m_objOutlookAdapter
End Function

Public Function ObterEValidarDestinatarios(ByRef strTo As String, ByRef strCC As String) As Boolean
    Const TO_PADRAO As String = "email1@empresa.com.br;email2@empresa.com.br"
    Const CC_PADRAO As String = "email3@empresa.com.br;email4@empresa.com.br"

    Dim objWs        As Worksheet
    Dim objTbl       As ListObject
    Dim objCol       As ListColumn
    Dim strTempTo    As String
    Dim strTempCC    As String
    Dim blnLeuConfig As Boolean
    Dim lngColPara   As Long
    Dim lngColCopia  As Long
    Dim strNomeCol   As String

    ' 1. Localiza a aba Config
    On Error Resume Next
    Set objWs = ThisWorkbook.Worksheets("Config")
    On Error GoTo 0
    If objWs Is Nothing Then
        GravarLogEx "Config: aba 'Config' nao encontrada. Usando destinatarios padrao.", LOG_WARNING
        GoTo Fallback
    End If

    ' 2. Localiza a tabela (tenta nomes conhecidos, depois qualquer tabela da aba)
    On Error Resume Next
    Set objTbl = objWs.ListObjects("EnderecosEmail")
    If objTbl Is Nothing Then Set objTbl = objWs.ListObjects("EnderecosEmailDestinatarios")
    If objTbl Is Nothing And objWs.ListObjects.count >= 1 Then Set objTbl = objWs.ListObjects(1)
    On Error GoTo 0

    If objTbl Is Nothing Then
        GravarLogEx "Config: nenhuma tabela encontrada na aba Config. Usando destinatarios padrao.", LOG_WARNING
        GoTo Fallback
    End If
    If objTbl.DataBodyRange Is Nothing Then
        GravarLogEx "Config: tabela '" & objTbl.Name & "' sem dados. Usando destinatarios padrao.", LOG_WARNING
        GoTo Fallback
    End If

    ' 3. Resolve colunas por sinonimos (case-insensitive) + fallback por posicao
    For Each objCol In objTbl.ListColumns
        strNomeCol = UCase$(Trim$(objCol.Name))
        If lngColPara = 0 Then
            If strNomeCol = "PARA" Or strNomeCol = "TO" Or strNomeCol = "DESTINATARIO" _
               Or InStr(strNomeCol, "EMAIL") > 0 Then lngColPara = objCol.index
        End If
        If lngColCopia = 0 Then
            If strNomeCol = "CC" Or strNomeCol = "COPIA" Or strNomeCol = "COM COPIA" Then lngColCopia = objCol.index
        End If
    Next objCol
    If lngColPara = 0 And objTbl.ListColumns.count >= 1 Then lngColPara = 1
    If lngColCopia = 0 And objTbl.ListColumns.count >= 2 Then lngColCopia = 2

    ' 4. Le os valores
    On Error Resume Next
    Err.Clear
    If lngColPara > 0 Then strTempTo = Trim$(CStr(objTbl.DataBodyRange.Cells(1, lngColPara).Value))
    If lngColCopia > 0 Then strTempCC = Trim$(CStr(objTbl.DataBodyRange.Cells(1, lngColCopia).Value))
    blnLeuConfig = (Err.Number = 0)
    On Error GoTo 0

    GravarLogEx "Config: tabela='" & objTbl.Name & "' | Para='" & strTempTo & "' | CC='" & strTempCC & "'", LOG_DEBUG

Fallback:
    strTo = IIf(blnLeuConfig And Len(strTempTo) > 0, Replace(strTempTo, " ", ""), TO_PADRAO)
    strCC = IIf(blnLeuConfig And Len(strTempCC) > 0, Replace(strTempCC, " ", ""), CC_PADRAO)

    ObterEValidarDestinatarios = (InStr(1, strTo, "@") > 0)
End Function

' ====================================================================================
' HTML - TABELA DE ERROS PARA O CORPO DO EMAIL
' ====================================================================================
Private Function GerarTabelaErrosHtml(ByRef arrErros() As DadosErro, ByVal lngQtd As Long) As String
    Const MAX_LINHAS_EMAIL As Long = 30

    Dim strHtml   As String
    Dim lngI      As Long
    Dim lngExibir As Long
    Dim strFundo  As String

    If lngQtd < 1 Then Exit Function
    lngExibir = IIf(lngQtd > MAX_LINHAS_EMAIL, MAX_LINHAS_EMAIL, lngQtd)

    strHtml = "<p style='font-size:10pt;margin-top:18px;'><b>" & HTML_ICON_CROSS & " Detalhamento dos erros encontrados:</b></p>"
    strHtml = strHtml & "<table style='border-collapse:collapse;width:100%;font-size:9pt;'>"
    strHtml = strHtml & "<tr style='background:#d32f2f;color:white;'>"
    strHtml = strHtml & "<th style='padding:6px 8px;border:1px solid #b71c1c;text-align:left;'>Num OB</th>"
    strHtml = strHtml & "<th style='padding:6px 8px;border:1px solid #b71c1c;text-align:left;'>Ref Cliente</th>"
    strHtml = strHtml & "<th style='padding:6px 8px;border:1px solid #b71c1c;text-align:left;'>Qtd NF</th>"
    strHtml = strHtml & "<th style='padding:6px 8px;border:1px solid #b71c1c;text-align:left;'>Tipo Erro</th>"
    strHtml = strHtml & "<th style='padding:6px 8px;border:1px solid #b71c1c;text-align:left;'>OBS_OB</th>"
    strHtml = strHtml & "</tr>"

    For lngI = 1 To lngExibir
        strFundo = IIf(lngI Mod 2 = 0, "#fff5f5", "#ffffff")
        With arrErros(lngI)
            strHtml = strHtml & "<tr style='background:" & strFundo & ";'>"
            strHtml = strHtml & "<td style='padding:5px 8px;border:1px solid #ddd;'>" & .NumOB & "</td>"
            strHtml = strHtml & "<td style='padding:5px 8px;border:1px solid #ddd;'>" & .refCliente & "</td>"
            strHtml = strHtml & "<td style='padding:5px 8px;border:1px solid #ddd;'>" & .qtpcnf & "</td>"
            strHtml = strHtml & "<td style='padding:5px 8px;border:1px solid #ddd;color:#b91c1c;font-weight:bold;'>" & .detalheErro & "</td>"
            strHtml = strHtml & "<td style='padding:5px 8px;border:1px solid #ddd;font-size:8pt;'>" & .ObsOB & "</td>"
            strHtml = strHtml & "</tr>"
        End With
    Next lngI

    strHtml = strHtml & "</table>"

    If lngQtd > MAX_LINHAS_EMAIL Then
        strHtml = strHtml & "<p style='font-size:9pt;color:#888;margin-top:8px;'>... e mais " & (lngQtd - MAX_LINHAS_EMAIL) & " erro(s). Consulte a aba <b>Erros NF</b> no Excel para ver todos.</p>"
    End If

    GerarTabelaErrosHtml = strHtml
End Function
