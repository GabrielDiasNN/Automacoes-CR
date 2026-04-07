Attribute VB_Name = "modNotificacaoNF"
Option Explicit

' ====================================================================================
' NOTIFICATION WRAPPERS
' ====================================================================================
Public Function ProcessarNotificacoesWrapper(ByRef udtTel As Telemetria, ByRef arrErros() As DadosErro, ByVal blnSilencioso As Boolean) As Boolean
    On Error Resume Next
    ProcessarNotificacoesWrapper = False

    GravarLogEx "Notificacoes | Total=" & udtTel.totalLinhas & " | Erros=" & udtTel.totalErros, LOG_DEBUG

    ' 1. Tentativa de Notificacao Customizada (plugin hook)
    ' Captura o retorno Boolean para distinguir o plugin que falhou silenciosamente
    ' (retornou False internamente sem propagar excecao) do que realmente funcionou.
    Dim blnPluginOk As Boolean
    On Error Resume Next
    Err.Clear
    blnPluginOk = modNotificacoesCustom.ProcessarNotificacoesCustomizadas(udtTel.totalLinhas, udtTel.totalErros, arrErros, blnSilencioso)

    If Err.Number = 0 And blnPluginOk Then
        ProcessarNotificacoesWrapper = True
    Else
        If Err.Number <> 0 Then GravarLogEx "Plugin falhou com excecao: " & Err.Description, LOG_WARNING
        If Not blnPluginOk Then GravarLogEx "Plugin retornou False - acionando fallback.", LOG_WARNING
    End If
    On Error GoTo 0
End Function

Public Sub FallbackNotificacaoPadrao(ByRef udtTel As Telemetria, ByRef arrErros() As DadosErro, ByVal objWs As Worksheet)
    On Error GoTo TratarErro

    GravarLogEx "Iniciando fallback de notificacao padrao (E-mail)...", LOG_INFO

    ' 1. Geracao de aba de erros para anexo/consulta
    If udtTel.totalErros > 0 Then
        GerarAbaErrosParaAnalise arrErros, udtTel.totalErros
        modEmailOutlook.PrepararErrosParaEmail arrErros, udtTel.totalErros
        EnviarEmailComErrosRetry udtTel
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
    Dim objWsErro   As Worksheet
    Dim objWsOrigem As Worksheet  ' planilha ativa antes da criacao - restaurada no final
    Dim objLo       As ListObject
    Dim lngI        As Long

    ' Guarda a aba original para restaurar depois da criacao.
    ' Worksheets.Add torna a nova aba o ActiveSheet; sem restaurar, o XLSM e
    ' salvo com "Erros NF" como aba ativa, contaminando execucoes futuras.
    On Error Resume Next
    Set objWsOrigem = ActiveSheet
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

    ' Restaura a planilha de dados como ativa para nao contaminar o ActiveSheet.
    On Error Resume Next
    If Not objWsOrigem Is Nothing Then objWsOrigem.Activate
    On Error GoTo 0

    GravarLogEx "Aba 'Erros NF' gerada com " & lngQtd & " registros.", LOG_DEBUG
End Sub
