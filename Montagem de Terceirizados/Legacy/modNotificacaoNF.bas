Attribute VB_Name = "modNotificacaoNF"
Option Explicit

' ====================================================================================
' NOTIFICATION WRAPPERS
' ====================================================================================
Public Function ProcessarNotificacoesWrapper(ByRef udtTel As Telemetria, ByRef arrErros() As DadosErro, ByVal blnSilencioso As Boolean) As Boolean
    On Error GoTo TratarErro
        ProcessarNotificacoesWrapper = False

        GravarLogEx "Notificacoes | Total=" & udtTel.totalLinhas & " | Erros=" & udtTel.totalErros, LOG_DEBUG

        ' 1. Tentativa de notificacao customizada
        ProcessarNotificacoesWrapper = modNotificacoesCustom.ProcessarNotificacoesCustomizadas(udtTel.totalLinhas, udtTel.totalErros, arrErros, blnSilencioso)

        If Not ProcessarNotificacoesWrapper Then
            GravarLogEx "Aviso: Notificacao customizada retornou falha.", LOG_WARNING
        End If

     Exit Function

TratarErro:
        GravarLogEx "Aviso: Notificacao customizada falhou por excecao: " & Err.Description, LOG_WARNING
        ProcessarNotificacoesWrapper = False
End Function

Public Sub FallbackNotificacaoPadrao(ByRef udtTel As Telemetria, ByRef arrErros() As DadosErro, ByVal objWs As Worksheet, _
    Optional ByVal strTipoNotificacao As String = NOTIF_TIPO_AUTO, _
    Optional ByVal lngTotalNovos As Long = 0, _
    Optional ByVal lngTotalCorrigidos As Long = 0, _
    Optional ByVal lngTotalPermanentes As Long = 0, _
    Optional ByVal strDeltaHtml As String = "")
    Dim strTipoEfetivo As String

    On Error GoTo TratarErro

        strTipoEfetivo = UCase$(Trim$(strTipoNotificacao))
        If Len(strTipoEfetivo) = 0 Or strTipoEfetivo = NOTIF_TIPO_AUTO Then
            If udtTel.totalErros > 0 Then
                strTipoEfetivo = NOTIF_TIPO_ERRO
            Else
                strTipoEfetivo = NOTIF_TIPO_ACERTO
            End If
        End If

        GravarLogEx "Iniciando fallback de notificacao padrao (E-mail) | Tipo=" & strTipoEfetivo & "...", LOG_INFO

        ' 1. Geracao de aba de erros para consulta
        If udtTel.totalErros > 0 Then
            GerarAbaErrosParaAnalise arrErros, udtTel.totalErros

            If strTipoEfetivo = NOTIF_TIPO_ALTERACAO Then
                EnviarEmailAlteracaoRetry udtTel, lngTotalNovos, lngTotalCorrigidos, lngTotalPermanentes, strDeltaHtml
            Else
                EnviarEmailComErrosRetry udtTel, arrErros, udtTel.totalErros
            End If
        Else
            EnviarEmailSucessoRetry udtTel
        End If

     Exit Sub

TratarErro:
        GravarLogEx "ERRO CRITICO no fallback de notificacao: " & Err.Description, LOG_ERROR
End Sub

' ====================================================================================
' REPORT GENERATION
' ====================================================================================
Private Sub GerarAbaErrosParaAnalise(ByRef arrErros() As DadosErro, ByVal lngQtd As Long)
    Dim objWsErro  As Worksheet
    Dim objLo      As ListObject
    Dim objWsAnterior As Worksheet
    Dim lngI       As Long

    On Error Resume Next
    Set objWsAnterior = ActiveSheet
    On Error GoTo 0

    On Error Resume Next
    Application.DisplayAlerts = False
    ThisWorkbook.Worksheets("Erros NF").Delete
    Application.DisplayAlerts = True
    On Error GoTo 0

        Set objWsErro = ThisWorkbook.Worksheets.Add(After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.count))
        objWsErro.Name = "Erros NF"

        ' Cabecalho fixo para analise rapida
        Dim varCabecalho As Variant
        varCabecalho = Array("Sit OB", "Progr", "Faccao", "Pcs Prog", "Num OB", "Kanban", "Fase Atual", "Status Fase", "Ref Cliente", "Qtd Pcs NF", "Obs OB", "Detalhe Erro", "Alternativo", "Timestamp")

        objWsErro.Range("A1").Resize(1, UBound(varCabecalho) + 1).Value = varCabecalho

        If lngQtd < 1 Then
            GravarLogEx "Aba 'Erros NF' gerada sem registros (lngQtd=0).", LOG_WARNING
         Exit Sub
        End If

        Dim varDados() As Variant
        ReDim varDados(1 To lngQtd, 1 To 14)

        For lngI = 1 To lngQtd
            With arrErros(lngI)
                varDados(lngI, 1) = .SitOB
                varDados(lngI, 2) = .Progr
                varDados(lngI, 3) = .Faccao
                varDados(lngI, 4) = .pcsProg
                varDados(lngI, 5) = .NumOB
                varDados(lngI, 6) = .Kanban
                varDados(lngI, 7) = .FaseAtual
                varDados(lngI, 8) = .StatusFase
                varDados(lngI, 9) = .refCliente
                varDados(lngI, 10) = .qtpcnf
                varDados(lngI, 11) = .ObsOB
                varDados(lngI, 12) = .detalheErro
                varDados(lngI, 13) = .Alternativo
                varDados(lngI, 14) = Now
            End With
        Next lngI

        objWsErro.Range("A2").Resize(lngQtd, 14).Value = varDados

        ' Criar ListObject para facilitar filtros
        Set objLo = objWsErro.ListObjects.Add(xlSrcRange, objWsErro.Range("A1").CurrentRegion, , xlYes)
        objLo.Name = "TabelaErrosNF_" & Format$(Now, "hhmmss")
        objLo.TableStyle = "TableStyleLight10"

        objWsErro.Columns.AutoFit
        GravarLogEx "Aba 'Erros NF' gerada com " & lngQtd & " registros.", LOG_DEBUG

        If Not objWsAnterior Is Nothing Then
            On Error Resume Next
            objWsAnterior.Activate
            On Error GoTo 0
        End If
End Sub

' ====================================================================================
' TESTES E2E (SUPORTE)
' ====================================================================================
Public Sub TestarEnvioSucesso()
    Dim udtTel As Telemetria
    udtTel.totalLinhas = 100
    udtTel.totalErros = 0
    udtTel.InicioExecucao = Timer
    
    EnviarEmailSucessoRetry udtTel
End Sub

Public Sub TestarEnvioErro()
    Dim udtTel As Telemetria
    Dim arrErros(1 To 1) As DadosErro
    
    udtTel.totalLinhas = 100
    udtTel.totalErros = 1
    udtTel.InicioExecucao = Timer
    
    arrErros(1).NumOB = "12345"
    arrErros(1).detalheErro = "Teste E2E - Divergencia de Quantidade"
    arrErros(1).Faccao = "FACCAO TESTE"
    
    EnviarEmailComErrosRetry udtTel, arrErros, 1
End Sub

Public Sub TestarEnvioAlteracao()
    Dim udtTel As Telemetria
    udtTel.totalLinhas = 100
    udtTel.totalErros = 5
    udtTel.InicioExecucao = Timer
    
    Dim strDelta As String
    strDelta = "<p>Teste E2E - Resumo de Alteracoes Simuladas</p>"
    
    EnviarEmailAlteracaoRetry udtTel, 2, 2, 1, strDelta
End Sub
