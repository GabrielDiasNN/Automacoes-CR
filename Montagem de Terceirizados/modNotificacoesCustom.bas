Attribute VB_Name = "modNotificacoesCustom"
Option Explicit

' ====================================================================================
' PRIVADOS (ESTADO / CONFIG)
' ====================================================================================
Private Type EstadoSistemaDetalhado
dtmSnapshot      As Date
lngTotalLinhas   As Long
lngTotalErros    As Long
strHashEstado    As String
End Type

Private Type MudancasDetectadas
arrNovos()       As DadosErro
arrCorrigidos()  As DadosErro
lngTotalNovos    As Long
lngTotalCorrigidos As Long
blnHouveMudanca  As Boolean
End Type

Private Const CACHE_ESTADO_FILE As String = "Cache_Estado_Detalhado.txt"
Private Const LIMITE_ANOMALIA    As Long = 50

' ====================================================================================
' ENTRY POINT (PLUGIN HOOK)
' ====================================================================================
Public Function ProcessarNotificacoesCustomizadas(ByVal lngTotalLinhas As Long, _
    ByVal lngTotalErros As Long, _
    ByRef arrErros() As DadosErro, _
    ByVal blnSilencioso As Boolean) As Boolean
    Dim udtEstadoAtual    As EstadoSistemaDetalhado
    Dim udtEstadoAnterior As EstadoSistemaDetalhado
    Dim udtMudancas       As MudancasDetectadas
    Dim blnAnomalia       As Boolean
    Dim udtTelLocal       As Telemetria

    On Error GoTo TratarErro
        ProcessarNotificacoesCustomizadas = False

        GravarLogEx "Iniciando ProcessarNotificacoesCustomizadas (Plugin)", LOG_DEBUG

        ' 1. Snapshot Do Estado
        With udtEstadoAtual
            .dtmSnapshot = Now
            .lngTotalLinhas = lngTotalLinhas
            .lngTotalErros = lngTotalErros
            .strHashEstado = GerarHashEstadoAtual(lngTotalLinhas, lngTotalErros, arrErros)
        End With

        ' 2. Carregar Cache e Comparar (Logica de Delta)
        udtEstadoAnterior = CarregarEstadoAnterior()
        udtMudancas = CompararEstados(udtEstadoAtual, udtEstadoAnterior)

        ' 3. Logica de anomalia
        blnAnomalia = (lngTotalErros >= LIMITE_ANOMALIA)
        If blnAnomalia Then
            GravarLogEx "ANOMALIA DETECTADA: Pico de erros (" & lngTotalErros & ")", LOG_WARNING
        End If

        ' 4. Persistencia (antes Do envio para evitar reenvio em Loop de erro)
        SalvarEstadoCache udtEstadoAtual

        ' 5. Notificacao por mudanca de estado ou anomalia
        If udtMudancas.blnHouveMudanca Or blnAnomalia Then
            GravarLogEx "Mudanca de estado detectada. Disparando notificacao de e-mail.", LOG_INFO
            With udtTelLocal
                .totalLinhas = lngTotalLinhas
                .totalErros = lngTotalErros
                .InicioExecucao = Timer
            End With
            ' VUL-07: FallbackNotificacaoPadrao ja trata totalErros=0 enviando e-mail
            ' de resolucao (EnviarEmailSucessoRetry). A guarda anterior (If lngTotalErros>0)
            ' suprimia esse envio, deixando destinatarios sem notificacao de correcao.
            '   VUL-04: envio isolado em On Error Resume Next para que falha no Outlook
            ' nao propague excecao ate o wrapper, evitando chamada dupla Do fallback.
            On Error Resume Next
            modNotificacaoNF.FallbackNotificacaoPadrao udtTelLocal, arrErros, Nothing
            If Err.Number <> 0 Then
                GravarLogEx "Falha ao enviar notificacao no plugin: " & Err.Description, LOG_WARNING
            End If
            Err.Clear
            On Error GoTo TratarErro
            Else
                GravarLogEx "Estado inalterado. Nenhuma notificacao necessaria.", LOG_DEBUG
            End If

            ProcessarNotificacoesCustomizadas = True
            GravarLogEx "ProcessarNotificacoesCustomizadas finalizado.", LOG_DEBUG
         Exit Function

TratarErro:
            GravarLogEx "ERRO no Plugin de Notificacao: " & Err.Description, LOG_ERROR
End Function

' ====================================================================================
' INTERNOS / AUXILIARES
' ====================================================================================
Private Function GerarHashEstadoAtual(ByVal lngLinhas As Long, ByVal lngErros As Long, ByRef arr() As DadosErro) As String
    Dim lngI    As Long
    Dim strBase As String
    Dim strResult As String

    ' Base estavel pelo contador - garante hash nao-vazio mesmo se array vazio
    strBase = CStr(lngLinhas) & "E" & CStr(lngErros) & ":"

    On Error Resume Next
    For lngI = 1 To lngErros
        strBase = strBase & CStr(arr(lngI).NumOB) & "|" & arr(lngI).detalheErro & ";"
        If Len(strBase) > 5000 Then Exit For
        Next lngI
        On Error GoTo 0

            strResult = modUtil.GerarHashDJB2(strBase)
            If Len(strResult) = 0 Then strResult = CStr(lngErros) & "fallback"
                GerarHashEstadoAtual = strResult
End Function

Private Function CarregarEstadoAnterior() As EstadoSistemaDetalhado
    Dim udtEstado  As EstadoSistemaDetalhado
    Dim intFileNum As Integer
    Dim strPath    As String
    Dim strLinha   As String
    Dim arrPartes() As String

    On Error GoTo Falha
        strPath = ThisWorkbook.Path & "\" & CACHE_ESTADO_FILE

        If Dir(strPath) = "" Then
            GravarLogEx "Cache anterior nao encontrado. Primeira execucao.", LOG_DEBUG
            GoTo Falha
            End If

            intFileNum = FreeFile
            Open strPath For Input As #intFileNum
            Line Input #intFileNum, strLinha
            Close #intFileNum

            arrPartes = Split(strLinha, "|")
            If UBound(arrPartes) >= 4 Then
                On Error Resume Next
                udtEstado.dtmSnapshot = CDate(arrPartes(0))
                udtEstado.lngTotalLinhas = CLng(arrPartes(1))
                udtEstado.lngTotalErros = CLng(arrPartes(2))
                udtEstado.strHashEstado = arrPartes(4)
                On Error GoTo Falha
                    GravarLogEx "Cache anterior: " & arrPartes(2) & " erros | Hash=" & arrPartes(4), LOG_DEBUG
                End If

Falha:
                CarregarEstadoAnterior = udtEstado
End Function

Private Function CompararEstados(ByRef udtAtual As EstadoSistemaDetalhado, ByRef udtAnterior As EstadoSistemaDetalhado) As MudancasDetectadas
    Dim udtMud As MudancasDetectadas

    ' Sem estado anterior (primeira execucao ou cache apagado) - trata erros como novos
    If udtAnterior.dtmSnapshot = 0 Then
        udtMud.blnHouveMudanca = (udtAtual.lngTotalErros > 0)
        If udtMud.blnHouveMudanca Then
            GravarLogEx "Sem estado anterior: " & udtAtual.lngTotalErros & " erro(s) encontrado(s) - notificando.", LOG_INFO
        End If
        CompararEstados = udtMud
     Exit Function
    End If

    ' Compara hash e contagem de erros
    If udtAtual.strHashEstado <> udtAnterior.strHashEstado Or _
        udtAtual.lngTotalErros <> udtAnterior.lngTotalErros Then
        udtMud.blnHouveMudanca = True
        GravarLogEx "Delta de estado: " & udtAnterior.lngTotalErros & " -> " & udtAtual.lngTotalErros & " erro(s). Hash: " & udtAnterior.strHashEstado & " -> " & udtAtual.strHashEstado, LOG_INFO
    Else
        GravarLogEx "Estado inalterado: " & udtAtual.lngTotalErros & " erro(s). Sem notificacao.", LOG_DEBUG
    End If

    CompararEstados = udtMud
End Function

' --------------------------------------------------------------------------------------------
' FUNCAO PARA GERACAO DE TABELA HTML (Pode ser usada por emails customizados)
' --------------------------------------------------------------------------------------------
Private Function GerarTabelaErrosHTML(ByRef arrErros() As DadosErro, ByVal lngTotal As Long) As String
    Dim strHtml     As String
    Dim lngI        As Long

    strHtml = "<table border='1' style='border-collapse:collapse; font-family:Calibri; font-size:10pt;'>"
    strHtml = strHtml & "<tr style='background-color:#D0CECE;'><th>OB</th><th>Progr</th><th>Erro</th></tr>"

    For lngI = 1 To lngTotal
        strHtml = strHtml & "<tr>"
        strHtml = strHtml & "<td>" & HTMLEncode(CStr(arrErros(lngI).NumOB)) & "</td>"
        strHtml = strHtml & "<td>" & HTMLEncode(CStr(arrErros(lngI).Progr)) & "</td>"
        strHtml = strHtml & "<td style='color:red;'>" & HTMLEncode(arrErros(lngI).detalheErro) & "</td>"
        strHtml = strHtml & "</tr>"
    Next lngI

    strHtml = strHtml & "</table>"
    GerarTabelaErrosHTML = strHtml
End Function

' --------------------------------------------------------------------------------------------
' PERSISTENCIA EM ARQUIVO
' --------------------------------------------------------------------------------------------
Private Sub SalvarEstadoCache(ByRef udtEstado As EstadoSistemaDetalhado)
    Dim intFileNum As Integer
    Dim strPath    As String
    Dim strLinha   As String

    On Error GoTo Falha
        strPath = ThisWorkbook.Path & "\" & CACHE_ESTADO_FILE
        intFileNum = FreeFile

        ' Formato: Data|Linhas|Erros|Alertas|Hash
        strLinha = Format$(udtEstado.dtmSnapshot, "dd/mm/yyyy hh:nn:ss") & "|" & _
        udtEstado.lngTotalLinhas & "|" & _
        udtEstado.lngTotalErros & "|0|" & _
        udtEstado.strHashEstado

        Open strPath For Output As #intFileNum
        Print #intFileNum, strLinha
        Close #intFileNum

        GravarLogEx "Cache atualizado: " & strPath, LOG_DEBUG
     Exit Sub
Falha:
        GravarLogEx "Erro ao salvar cache: " & Err.Description, LOG_WARNING
End Sub

Private Function HTMLEncode(ByVal strIn As String) As String
    strIn = Replace(strIn, "&", "&amp;")
    strIn = Replace(strIn, "<", "&lt;")
    strIn = Replace(strIn, ">", "&gt;")
    strIn = Replace(strIn, """", "&quot;")
    HTMLEncode = strIn
End Function

' VUL-09: GerarHashDJB2 removida deste modulo.
' Uso centralizado em modUtil.GerarHashDJB2 (canonica, ASCII-safe, Hex output).
