Attribute VB_Name = "modEmailOutlook"
Option Explicit

Private m_objOutlookAdapter As ClsOutlookAdapter
Private m_strLastEmailKey As String

' ====================================================================================
' RETRY WRAPPERS
' ====================================================================================
Public Sub EnviarEmailComErrosRetry(ByRef udtTel As Telemetria, ByRef arrErros() As DadosErro, ByVal lngTotalErrosDetalhe As Long)
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
        If EnviarEmailComErros(udtTel, arrErros, lngTotalErrosDetalhe) Then
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

Public Sub EnviarEmailAlteracaoRetry(ByRef udtTel As Telemetria, ByVal lngTotalNovos As Long, ByVal lngTotalCorrigidos As Long, ByVal lngTotalPermanentes As Long, ByVal strDeltaHtml As String)
    Dim lngTentativa      As Long
    Dim lngDelaySegundos  As Long
    Dim strEmailKey       As String

    strEmailKey = MontarEmailKeyExecucao("ALTERACAO", udtTel) & "|" & CStr(lngTotalNovos) & "|" & CStr(lngTotalCorrigidos) & "|" & CStr(lngTotalPermanentes)
    If JaNotificacaoEnviada(strEmailKey) Then
        GravarLogEx "Email ALTERACAO ignorado por idempotencia no mesmo run.", LOG_WARNING
     Exit Sub
    End If

    For lngTentativa = 1 To MAX_EMAIL_RETRIES
        GravarLogEx "Email ALTERACAO | tentativa " & lngTentativa & "/" & MAX_EMAIL_RETRIES, LOG_INFO
        If EnviarEmailAlteracao(udtTel, lngTotalNovos, lngTotalCorrigidos, lngTotalPermanentes, strDeltaHtml) Then
            RegistrarNotificacaoEnviada strEmailKey
         Exit Sub
        End If

        If lngTentativa < MAX_EMAIL_RETRIES Then
            lngDelaySegundos = RETRY_DELAY_BASE ^ lngTentativa
            GravarLogEx "Email ALTERACAO falhou. Aguardando " & lngDelaySegundos & "s...", LOG_WARNING
            Application.Wait Now + TimeSerial(0, 0, CInt(lngDelaySegundos))
        End If
    Next lngTentativa

    GravarLogEx "FALHA DEFINITIVA: Email ALTERACAO nao enviado.", LOG_ERROR
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
    If Not m_objOutlookAdapter Is Nothing Then
        m_objOutlookAdapter.ResetState
    End If
End Sub

' ====================================================================================
' CONSTRUTORES DE EMAIL
' ====================================================================================
Private Function EnviarEmailComErros(ByRef udtTel As Telemetria, ByRef arrErros() As DadosErro, ByVal lngTotalErrosDetalhe As Long) As Boolean
    Dim strTo      As String, strCC As String
    Dim strHtml    As String, strAssunto As String
    Dim strIntro   As String
    Dim strLegenda As String
    Dim strTabelaErrosHtml As String

    If Not ObterEValidarDestinatarios(strTo, strCC) Then
        EnviarEmailComErros = False: Exit Function
    End If

    strIntro = "Segue relat" & ChrW$(243) & "rio automatizado da valida" & ChrW$(231) & "" & ChrW$(227) & "o de notas fiscais."
    strLegenda = "<span style='color:#b91c1c;font-weight:bold;'>Aten&ccedil;&atilde;o: diverg&ecirc;ncias detectadas. A lista completa est&aacute; detalhada neste e-mail.</span>"
    strTabelaErrosHtml = MontarTabelaCompletaErrosHtml(arrErros, lngTotalErrosDetalhe)
    strHtml = MontarTemplateEmail(NOTIF_TIPO_ERRO, udtTel, strTabelaErrosHtml)
    strAssunto = "[ALERTA] Diverg" & ChrW$(234) & "ncias - Controle NF - " & FormatarDataBR(Now)

    EnviarEmailComErros = EnviarEmailCore(strAssunto, strHtml, strTo, strCC, "", strIntro, strLegenda)
End Function

Private Function EnviarEmailAlteracao(ByRef udtTel As Telemetria, ByVal lngTotalNovos As Long, ByVal lngTotalCorrigidos As Long, ByVal lngTotalPermanentes As Long, ByVal strDeltaHtml As String) As Boolean
    Dim strTo      As String, strCC As String
    Dim strHtml    As String, strAssunto As String
    Dim strIntro   As String
    Dim strLegenda As String

    If Not ObterEValidarDestinatarios(strTo, strCC) Then
        EnviarEmailAlteracao = False: Exit Function
    End If

    strIntro = "Segue relat" & ChrW$(243) & "rio automatizado da valida" & ChrW$(231) & "" & ChrW$(227) & "o de notas fiscais."
    strLegenda = "<span style='color:#b45309;font-weight:bold;'>Altera&ccedil;&atilde;o detectada: " & _
    CStr(lngTotalNovos) & " novos, " & CStr(lngTotalCorrigidos) & " corrigidos e " & CStr(lngTotalPermanentes) & " permanentes.</span>"
    strHtml = MontarTemplateEmail(NOTIF_TIPO_ALTERACAO, udtTel, strDeltaHtml)
    strAssunto = "[ALTERA" & ChrW$(199) & ChrW$(195) & "O] Diverg" & ChrW$(234) & "ncias - Controle NF - " & FormatarDataBR(Now)

    EnviarEmailAlteracao = EnviarEmailCore(strAssunto, strHtml, strTo, strCC, "", strIntro, strLegenda)
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
    strHtml = MontarTemplateEmail(NOTIF_TIPO_ACERTO, udtTel, vbNullString)
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
        EnviarEmailCore = objAdapter.EnviarEmailHtml(strSubject, strBodyHtml, strTo, strCC, strAttachmentPath, strIntro, strLegenda)

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
Private Function MontarTemplateEmail(ByVal strTipoNotificacao As String, ByRef udtTel As Telemetria, Optional ByVal strDetalhesHtml As String = "") As String
    Dim strHtml As String
    Dim strCor  As String
    Dim strIcon As String
    Dim strMsg  As String
    Dim strResultado As String
    Dim strTipo As String

    strTipo = UCase$(Trim$(strTipoNotificacao))

    Select Case strTipo
     Case NOTIF_TIPO_ERRO
        strCor = "#d32f2f"
        strIcon = HTML_ICON_WARNING
        strMsg = "Diverg&ecirc;ncias Detectadas"
        strResultado = CStr(udtTel.totalErros) & " erros"
     Case NOTIF_TIPO_ALTERACAO
        strCor = "#ef6c00"
        strIcon = HTML_ICON_TARGET
        strMsg = "Diverg&ecirc;ncias Alteradas"
        strResultado = CStr(udtTel.totalErros) & " erros"
     Case Else
        strCor = "#388e3c"
        strIcon = HTML_ICON_CHECK
        strMsg = "Valida&ccedil;&atilde;o Aprovada"
        strResultado = "100% OK"
    End Select

    strHtml = "<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body style='margin:0;padding:16px;background:#f3f4f6;'>"
    strHtml = strHtml & "<div style='font-family:Calibri,Arial,sans-serif;font-size:11pt;max-width:920px;margin:0 auto;color:#1f2937;'>"
    strHtml = strHtml & "<div style='background:linear-gradient(135deg," & strCor & " 0%,#1f2937 100%);padding:20px 24px;border-radius:10px 10px 0 0;'>"
    strHtml = strHtml & "<h1 style='color:#ffffff;margin:0;font-size:22pt;text-align:center;line-height:1.2;'><span style='font-size:30pt;vertical-align:middle;'>" & strIcon & "</span> " & strMsg & "</h1></div>"
    strHtml = strHtml & "<div style='background:#ffffff;padding:22px;border:1px solid #d1d5db;border-top:none;border-radius:0 0 10px 10px;'>"

    Select Case strTipo
     Case NOTIF_TIPO_ERRO
          strHtml = strHtml & "<p style='font-size:12pt;margin:0 0 8px 0;text-align:center;'><span style='font-size:14pt;'>" & HTML_ICON_MAGNIFY & "</span> <b>Foram detectadas diverg&ecirc;ncias na valida&ccedil;&atilde;o.</b></p>"
          strHtml = strHtml & "<p style='font-size:11pt;margin:0 0 12px 0;text-align:center;'><span style='font-size:14pt;'>" & HTML_ICON_PACKAGE & "</span> A rela&ccedil;&atilde;o completa dos itens est&aacute; no corpo deste e-mail.</p>"
     Case NOTIF_TIPO_ALTERACAO
          strHtml = strHtml & "<p style='font-size:12pt;margin:0 0 8px 0;text-align:center;'><span style='font-size:14pt;'>" & HTML_ICON_CHART_UP & "</span> <b>Foi detectada altera&ccedil;&atilde;o no conjunto de diverg&ecirc;ncias.</b></p>"
          strHtml = strHtml & "<p style='font-size:11pt;margin:0 0 12px 0;text-align:center;'><span style='font-size:14pt;'>" & HTML_ICON_PACKAGE & "</span> Confira abaixo o detalhamento com novos, corrigidos e permanentes.</p>"
     Case Else
          strHtml = strHtml & "<p style='font-size:12pt;margin:0 0 12px 0;text-align:center;'><span style='font-size:14pt;'>" & HTML_ICON_TROPHY & "</span> <b>Nenhuma diverg&ecirc;ncia encontrada na valida&ccedil;&atilde;o.</b></p>"
    End Select

     strHtml = strHtml & "<div style='background:#f9fafb;border:1px solid #e5e7eb;border-left:4px solid " & strCor & ";padding:12px;margin:18px 0;border-radius:6px;'>"
     strHtml = strHtml & "<table role='presentation' border='0' cellspacing='0' cellpadding='6' width='100%' style='border-collapse:collapse;text-align:center;'>"
     strHtml = strHtml & "<tr>"
     strHtml = strHtml & "<td style='width:33%;font-size:10pt;color:#4b5563;'><span style='font-size:15pt;'>" & HTML_ICON_CHART & "</span><br><b>Total de linhas</b><br><span style='font-size:14pt;color:#111827;">" & udtTel.totalLinhas & "</span></td>"
     strHtml = strHtml & "<td style='width:33%;font-size:10pt;color:#4b5563;'><span style='font-size:15pt;'>" & IIf(strTipo = NOTIF_TIPO_ACERTO, HTML_ICON_CHECK, HTML_ICON_CROSS) & "</span><br><b>Resultado</b><br><span style='font-size:14pt;color:#111827;">" & strResultado & "</span></td>"
     strHtml = strHtml & "<td style='width:33%;font-size:10pt;color:#4b5563;'><span style='font-size:15pt;'>" & HTML_ICON_STOPWATCH & "</span><br><b>Tempo de processamento</b><br><span style='font-size:14pt;color:#111827;">" & Format$(TimerElapsed(udtTel.InicioExecucao), "0.00") & "s</span></td>"
     strHtml = strHtml & "</tr></table></div>"

    If Len(Trim$(strDetalhesHtml)) > 0 Then
        strHtml = strHtml & "<div style='margin-top:18px;'>" & strDetalhesHtml & "</div>"
    End If

    strHtml = strHtml & "<hr style='border:0;border-top:1px solid #ddd;margin:26px 0;'>"
    strHtml = strHtml & "<p style='font-size:9pt;color:#6b7280;text-align:center;'><span style='font-size:12pt;'>" & HTML_ICON_ROBOT & "</span> <i>Rob" & ChrW$(244) & " Fiscal " & ROBO_VERSAO_DASH & "</i><br>"
    strHtml = strHtml & "<span style='font-size:12pt;'>" & HTML_ICON_CALENDAR & "</span> Data/Hora: <b>" & FormatarDataBR(Now, True) & "</b></p>"
    strHtml = strHtml & "</div></div></body></html>"

    MontarTemplateEmail = strHtml
End Function

Private Function MontarTabelaCompletaErrosHtml(ByRef arrErros() As DadosErro, ByVal lngTotal As Long) As String
    Dim strHtml As String
    Dim lngI As Long
    Dim lngTotalValido As Long

    On Error GoTo Falha

        lngTotalValido = lngTotal
        If lngTotalValido < 1 Then
            MontarTabelaCompletaErrosHtml = "<p style='font-size:10pt;color:#555;'><i>Sem itens detalhados para exibir.</i></p>"
         Exit Function
        End If

        strHtml = "<p style='font-size:11pt;margin:0 0 10px 0;text-align:center;'><b>Detalhamento completo das diverg&ecirc;ncias identificadas:</b></p>"
        strHtml = strHtml & "<div style='overflow-x:auto;'>"
        strHtml = strHtml & "<table border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse;font-family:Calibri,Arial,sans-serif;font-size:9.5pt;width:100%;table-layout:fixed;'>"
        strHtml = strHtml & "<tr style='background-color:#fdecec;text-align:center;'>"
        strHtml = strHtml & "<th>Sit. OB</th><th>Prog.</th><th>Fac&ccedil;&atilde;o</th><th>Pe&ccedil;as Prog.</th><th>N&ordm; OB</th><th>Kanban</th><th>Fase Atual</th><th>Status Fase</th><th>Refer&ecirc;ncia Cliente</th><th>Qtd. Pe&ccedil;as NF</th><th>Observa&ccedil;&atilde;o OB</th><th>Detalhe do Erro</th><th>Alternativo</th><th>Data/Hora</th>"
        strHtml = strHtml & "</tr>"

        For lngI = 1 To lngTotalValido
            strHtml = strHtml & "<tr style='text-align:center;'>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).SitOB) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).Progr) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).Faccao) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).pcsProg) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).NumOB) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).Kanban) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).FaseAtual) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).StatusFase) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).refCliente) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).qtpcnf) & "</td>"
            strHtml = strHtml & "<td style='text-align:left;'>" & SafeTextoHtml(arrErros(lngI).ObsOB) & "</td>"
            strHtml = strHtml & "<td style='text-align:left;'>" & SafeTextoHtml(arrErros(lngI).detalheErro) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(arrErros(lngI).Alternativo) & "</td>"
            strHtml = strHtml & "<td>" & SafeTextoHtml(FormatarDataBR(Now, True)) & "</td>"
            strHtml = strHtml & "</tr>"
        Next lngI

        strHtml = strHtml & "</table></div>"
        MontarTabelaCompletaErrosHtml = strHtml
     Exit Function

Falha:
        MontarTabelaCompletaErrosHtml = "<p style='font-size:10pt;color:#b91c1c;'><b>Falha ao montar tabela completa de erros para o e-mail.</b></p>"
End Function

Private Function SafeTextoHtml(ByVal varValor As Variant) As String
    Dim strOut As String

    On Error Resume Next
    strOut = CStr(varValor)
    On Error GoTo 0

        strOut = Replace(strOut, "&", "&amp;")
        strOut = Replace(strOut, "<", "&lt;")
        strOut = Replace(strOut, ">", "&gt;")
        strOut = Replace(strOut, """", "&quot;")
        strOut = Replace(strOut, "'", "&#39;")

        SafeTextoHtml = strOut
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

Private Function NormalizarNomeColuna(ByVal strValor As String) As String
    Dim strOut As String

    strOut = UCase$(Trim$(strValor))

    strOut = Replace(strOut, ChrW$(192), "A")
    strOut = Replace(strOut, ChrW$(193), "A")
    strOut = Replace(strOut, ChrW$(194), "A")
    strOut = Replace(strOut, ChrW$(195), "A")
    strOut = Replace(strOut, ChrW$(196), "A")
    strOut = Replace(strOut, ChrW$(224), "A")
    strOut = Replace(strOut, ChrW$(225), "A")
    strOut = Replace(strOut, ChrW$(226), "A")
    strOut = Replace(strOut, ChrW$(227), "A")
    strOut = Replace(strOut, ChrW$(228), "A")

    strOut = Replace(strOut, ChrW$(200), "E")
    strOut = Replace(strOut, ChrW$(201), "E")
    strOut = Replace(strOut, ChrW$(202), "E")
    strOut = Replace(strOut, ChrW$(203), "E")
    strOut = Replace(strOut, ChrW$(232), "E")
    strOut = Replace(strOut, ChrW$(233), "E")
    strOut = Replace(strOut, ChrW$(234), "E")
    strOut = Replace(strOut, ChrW$(235), "E")

    strOut = Replace(strOut, ChrW$(204), "I")
    strOut = Replace(strOut, ChrW$(205), "I")
    strOut = Replace(strOut, ChrW$(206), "I")
    strOut = Replace(strOut, ChrW$(207), "I")
    strOut = Replace(strOut, ChrW$(236), "I")
    strOut = Replace(strOut, ChrW$(237), "I")
    strOut = Replace(strOut, ChrW$(238), "I")
    strOut = Replace(strOut, ChrW$(239), "I")

    strOut = Replace(strOut, ChrW$(210), "O")
    strOut = Replace(strOut, ChrW$(211), "O")
    strOut = Replace(strOut, ChrW$(212), "O")
    strOut = Replace(strOut, ChrW$(213), "O")
    strOut = Replace(strOut, ChrW$(214), "O")
    strOut = Replace(strOut, ChrW$(242), "O")
    strOut = Replace(strOut, ChrW$(243), "O")
    strOut = Replace(strOut, ChrW$(244), "O")
    strOut = Replace(strOut, ChrW$(245), "O")
    strOut = Replace(strOut, ChrW$(246), "O")

    strOut = Replace(strOut, ChrW$(217), "U")
    strOut = Replace(strOut, ChrW$(218), "U")
    strOut = Replace(strOut, ChrW$(219), "U")
    strOut = Replace(strOut, ChrW$(220), "U")
    strOut = Replace(strOut, ChrW$(249), "U")
    strOut = Replace(strOut, ChrW$(250), "U")
    strOut = Replace(strOut, ChrW$(251), "U")
    strOut = Replace(strOut, ChrW$(252), "U")

    strOut = Replace(strOut, ChrW$(199), "C")
    strOut = Replace(strOut, ChrW$(231), "C")

    NormalizarNomeColuna = strOut
End Function

Private Function ObterValorColunaTabela(ByRef objTbl As ListObject, ByVal strNomeColuna As String) As String
    Dim objCol As ListColumn
    Dim strAlvo As String

    strAlvo = NormalizarNomeColuna(strNomeColuna)

    For Each objCol In objTbl.ListColumns
        If NormalizarNomeColuna(CStr(objCol.Name)) = strAlvo Then
            If Not objCol.DataBodyRange Is Nothing Then
                ObterValorColunaTabela = CStr(objCol.DataBodyRange.Cells(1, 1).Value)
            End If
         Exit Function
        End If
    Next objCol

    ObterValorColunaTabela = ""
End Function

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
            strTempTo = ObterValorColunaTabela(objTbl, "Para")
            strTempCC = ObterValorColunaTabela(objTbl, "Copia")

            blnLeuConfig = (Len(Trim$(strTempTo)) > 0 Or Len(Trim$(strTempCC)) > 0)
        End If

        If Len(Trim$(strTempTo)) = 0 Then
            strTempTo = CStr(objWs.Range("B2").Value)
            If Err.Number = 0 Then blnLeuConfig = True
            End If

            If Len(Trim$(strTempCC)) = 0 Then
                strTempCC = CStr(objWs.Range("B3").Value)
                If Err.Number = 0 Then blnLeuConfig = True
                End If
            End If
            On Error GoTo 0

                strTo = IIf(blnLeuConfig And Len(Trim$(strTempTo)) > 0, Replace(Trim$(strTempTo), " ", ""), TO_PADRAO)
                strCC = IIf(blnLeuConfig And Len(Trim$(strTempCC)) > 0, Replace(Trim$(strTempCC), " ", ""), CC_PADRAO)

                If strTo = TO_PADRAO Then
                    GravarLogEx "E-MAIL: destinatarios PARA em fallback padrao (Config vazia/ausente).", LOG_WARNING
                End If

                If strCC = CC_PADRAO Then
                    GravarLogEx "E-MAIL: destinatarios CC em fallback padrao (Config vazia/ausente).", LOG_WARNING
                End If

                ObterEValidarDestinatarios = (InStr(1, strTo, "@") > 0)
End Function
