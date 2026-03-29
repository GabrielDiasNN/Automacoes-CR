Attribute VB_Name = "modMain"
Option Explicit

' ====================================================================================
' PRIVATE STATE
' ====================================================================================
Private m_Telemetria  As Telemetria
Private m_OutlookApp  As Object

' ====================================================================================
' ENTRY POINT
' ====================================================================================
Public Sub AtualizarEValidar(Optional ByVal blnModoRobo As Boolean = False, _
                              Optional ByVal strExecId As String = "")
    On Error GoTo TratarErro

    Dim objContexto     As clsAppContext
    Dim objConexaoAlvo  As WorkbookConnection
    Dim strFpAntes      As String
    Dim strFpDepois     As String
    Dim blnStampOK      As Boolean
    Dim varStampAntes   As Variant
    Dim varStampDepois  As Variant
    Dim strStampAntesK  As String
    Dim strStampDepoisK As String
    Dim dblTempoInicio  As Double

    ' 1. Inicializacao do Contexto
    Set objContexto = New clsAppContext
    With objContexto
        .ModoRobo = blnModoRobo
        Set .WorkbookAlvo = ThisWorkbook
        If strExecId <> "" Then
            .RunId = strExecId
            DefinirRunId strExecId
        Else
            Call IniciarRunId(True)
            .RunId = GetRunId()
        End If
    End With

    LimparEstadoNotificacao
    LimparTelemetriaExecucao

    InicializarAplicacao objContexto

    m_Telemetria.InicioExecucao = Timer
    GravarLogEx LOG_SEPARADOR_DUPLO, LOG_INFO
    GravarLogEx "INICIO. Modo Robo: " & IIf(blnModoRobo, "Sim", "Nao") & _
                " | Versao: " & ROBO_VERSAO_TEXTO, LOG_INFO

    ' 2. Pre-condicoes
    LogStepStart "PRECOND"
    ValidarPreCondicoes objContexto
    LogStepEnd "OK"

    ' 3. Refresh Oracle
    LogStepStart "REFRESH"
    Set objConexaoAlvo = FindConnectionByPartialName(STAMP_TABLE_NAME)
    If objConexaoAlvo Is Nothing Then
        Err.Raise vbObjectError + 701, "modMain", "Conexao '" & STAMP_TABLE_NAME & "' nao encontrada."
    End If

    ' Snapshot ANTES
    strFpAntes = ObterFingerprintTabelaAtiva() ' TODO: Mudar para aceitar ws explicito
    On Error Resume Next
    EnsureStampNamedRange
    blnStampOK = (Err.Number = 0)
    Err.Clear
    On Error GoTo TratarErro

    If blnStampOK Then
        varStampAntes = GetStampValue()
        strStampAntesK = StampKey(varStampAntes)
        LogStampSnapshot "ANTES", varStampAntes
    End If

    If Not blnModoRobo Then Application.StatusBar = ">> [10%] Atualizando Oracle..."

    GravarLogEx "Refresh Oracle: inicio | Conexao='" & objConexaoAlvo.Name & "'", LOG_INFO
    dblTempoInicio = Timer

    ExecutarRefreshSincrono objConexaoAlvo

    GravarLogEx "Refresh Oracle: fim | Duracao=" & Format$(TimerElapsed(dblTempoInicio), "0.00") & "s", LOG_INFO
    LogStepEnd "Refresh concluido"

    ' Snapshot DEPOIS + Validacao STAMP
    If blnStampOK Then
        varStampDepois = GetStampValue()
        strStampDepoisK = StampKey(varStampDepois)
        LogStampSnapshot "DEPOIS", varStampDepois

        ValidarMudancaStamp strStampAntesK, strStampDepoisK, blnModoRobo
    End If

    ' Salvar se modo robo
    If blnModoRobo Then ThisWorkbook.Save

    ' 4. Validacao de Dados
    If Not blnModoRobo Then Application.StatusBar = ">> [50%] Validando dados..."
    LogStepStart "VALIDAR"
    ' Passamos o contexto ou a sheet resolvida.
    ' Passamos o contexto ou a sheet resolvida.
    Call ValidarNotasFiscais(m_Telemetria, blnSilencioso:=blnModoRobo, blnGerenciarConfig:=False)
    LogStepEnd "Validacao concluida"

    ' 5. Dashboard e Finalizacao
    LogStepStart "DASH"
    RegistrarHistorico True, m_Telemetria
    LogStepEnd "OK"

    GravarLogEx "FIM DO PROCESSO. Resultado=Sucesso | Tempo=" & Format$(TimerElapsed(m_Telemetria.InicioExecucao), "0.00") & "s", LOG_INFO

    If Not blnModoRobo Then
        MsgBox "Processo concluido!" & vbCrLf & _
               "Linhas: " & m_Telemetria.totalLinhas & vbCrLf & _
               "Erros: " & m_Telemetria.totalErros, vbInformation
    End If

SaidaLimpa:
    FinalizarAplicacao objContexto
    Set objContexto = Nothing
    Exit Sub

TratarErro:
    Dim strErro As String
    strErro = "ERRO FATAL: " & Err.Description & " [Num: " & Err.Number & "]"
    GravarLogEx strErro, LOG_ERROR
    If Not blnModoRobo Then MsgBox strErro, vbCritical
    On Error Resume Next
    RegistrarHistorico False, m_Telemetria
    Resume SaidaLimpa
End Sub

' ====================================================================================
' AUXILIARES DE ORQUESTRACAO
' ====================================================================================

Private Sub ValidarPreCondicoes(ByVal objContexto As clsAppContext)
    If objContexto Is Nothing Then Err.Raise vbObjectError + 500, "ValidarPreCondicoes", "Contexto nulo"

    If objContexto.WorkbookAlvo.Path = "" Then
        Err.Raise vbObjectError + 501, "ValidarPreCondicoes", "O arquivo deve ser salvo antes de executar."
    End If

    If objContexto.WorkbookAlvo.Connections.count = 0 Then
        Err.Raise vbObjectError + 502, "ValidarPreCondicoes", "Nenhuma conexao encontrada no Workbook."
    End If
End Sub

Private Sub LimparTelemetriaExecucao()
    With m_Telemetria
        .InicioExecucao = 0#
        .FimConexao = 0#
        .FimValidacao = 0#
        .FimEmail = 0#
        .totalLinhas = 0
        .totalErros = 0
    End With
End Sub

Private Sub ExecutarRefreshSincrono(ByVal objConexao As Object)
    On Error GoTo TratarErro

    Dim lngTipoConexao As Long
    Dim blnRefreshDireto As Boolean

    On Error Resume Next
    lngTipoConexao = CLng(objConexao.Type)
    On Error GoTo TratarErro

    GravarLogEx "Refresh Oracle: tipo de conexao=" & CStr(lngTipoConexao), LOG_DEBUG

    blnRefreshDireto = ConfigurarConexaoRefresh(objConexao)

    If blnRefreshDireto Then
        GravarLogEx "Refresh Oracle: executando objConexao.Refresh", LOG_DEBUG
        objConexao.Refresh
    Else
        ' Fallback para conexoes nao OLEDB/ODBC (ex.: Power Query/Data Model)
        GravarLogEx "Refresh Oracle: usando fallback ThisWorkbook.RefreshAll", LOG_WARNING
        ThisWorkbook.RefreshAll
    End If

    On Error Resume Next
    Application.CalculateUntilAsyncQueriesDone
    If Err.Number <> 0 Then
        GravarLogEx "Refresh Oracle: CalculateUntilAsyncQueriesDone retornou erro " & Err.Number & " - " & Err.Description, LOG_WARNING
        Err.Clear
    End If
    On Error GoTo TratarErro

    Exit Sub

TratarErro:
    Err.Raise vbObjectError + 704, "ExecutarRefreshSincrono", "Falha no refresh Oracle: " & Err.Description
End Sub

Private Function ConfigurarConexaoRefresh(ByVal objConexao As Object) As Boolean
    Dim blnConfigurado As Boolean

    On Error Resume Next

    Err.Clear
    objConexao.OLEDBConnection.BackgroundQuery = False
    objConexao.OLEDBConnection.CommandTimeout = ORACLE_TIMEOUT_SECONDS
    If Err.Number = 0 Then
        blnConfigurado = True
        GravarLogEx "Refresh Oracle: timeout OLEDB=" & ORACLE_TIMEOUT_SECONDS & "s", LOG_DEBUG
    End If

    Err.Clear
    objConexao.ODBCConnection.BackgroundQuery = False
    objConexao.ODBCConnection.CommandTimeout = ORACLE_TIMEOUT_SECONDS
    If Err.Number = 0 Then
        blnConfigurado = True
        GravarLogEx "Refresh Oracle: timeout ODBC=" & ORACLE_TIMEOUT_SECONDS & "s", LOG_DEBUG
    End If

    On Error GoTo 0

    If Not blnConfigurado Then
        GravarLogEx "Refresh Oracle: timeout de conexao nao aplicado (tipo de conexao nao suportado).", LOG_WARNING
    End If

    ConfigurarConexaoRefresh = blnConfigurado
End Function

Private Sub ValidarMudancaStamp(ByVal strAntes As String, ByVal strDepois As String, ByVal blnModoRobo As Boolean)
    If IsStampInconclusivoPorTabelaVazia() Then
        GravarLogEx "Stamp: INCONCLUSIVO (tabela vazia)", LOG_WARNING
    ElseIf Len(strAntes) > 0 And Len(strDepois) > 0 Then
        If StrComp(strAntes, strDepois, vbBinaryCompare) = 0 Then
            GravarLogEx "Stamp: NAO MUDOU | Valor=" & strAntes, LOG_ERROR
            If blnModoRobo Then
                Err.Raise vbObjectError + 703, "ValidarMudancaStamp", "Dados nao foram atualizados no Oracle (STAMP identico)."
            End If
        Else
            GravarLogEx "Stamp: MUDOU | " & strAntes & " -> " & strDepois, LOG_INFO
        End If
    End If
End Sub

' ====================================================================================
' GESTAO DE ESTADO DO EXCEL (ENGINE)
' ====================================================================================

Public Sub InicializarAplicacao(ByVal objContexto As clsAppContext)
    If objContexto Is Nothing Then Exit Sub

    With Application
        objContexto.ScreenUpdatingOriginal = .ScreenUpdating
        objContexto.EnableEventsOriginal = .EnableEvents
        objContexto.DisplayAlertsOriginal = .DisplayAlerts
        objContexto.CalculationOriginal = .Calculation

        .ScreenUpdating = False
        .EnableEvents = False
        .DisplayAlerts = False
        .Calculation = xlCalculationManual
    End With
End Sub

Public Sub FinalizarAplicacao(ByVal objContexto As clsAppContext)
    On Error Resume Next ' Garante restauracao mesmo se houver erro no contexto

    If objContexto Is Nothing Then
        With Application
            .ScreenUpdating = True
            .EnableEvents = True
            .DisplayAlerts = True
            .Calculation = xlCalculationAutomatic
            .StatusBar = False
        End With
    Else
        With Application
            .ScreenUpdating = objContexto.ScreenUpdatingOriginal
            .EnableEvents = objContexto.EnableEventsOriginal
            .DisplayAlerts = objContexto.DisplayAlertsOriginal
            .Calculation = objContexto.CalculationOriginal
            .StatusBar = False
        End With
    End If

    Set m_OutlookApp = Nothing
    On Error GoTo 0
End Sub
