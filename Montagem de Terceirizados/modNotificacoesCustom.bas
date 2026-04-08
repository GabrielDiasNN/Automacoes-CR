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
arrNovos()           As DadosErro
arrCorrigidos()      As DadosErro
arrPermanentes()     As DadosErro
lngTotalNovos        As Long
lngTotalCorrigidos   As Long
lngTotalPermanentes  As Long
blnHouveMudanca      As Boolean
strTipoNotificacao   As String
End Type

Private Const CACHE_ESTADO_FILE As String = "Cache_Estado_Detalhado.txt"
Private Const CACHE_ITENS_FILE As String = "Cache_Estado_Itens.txt"
Private Const LIMITE_ANOMALIA As Long = 50

' ====================================================================================
' ENTRY POINT (PLUGIN HOOK)
' ====================================================================================
Public Function ProcessarNotificacoesCustomizadas(ByVal lngTotalLinhas As Long, _
    ByVal lngTotalErros As Long, _
    ByRef arrErros() As DadosErro, _
    ByVal blnSilencioso As Boolean) As Boolean
    Dim udtEstadoAtual As EstadoSistemaDetalhado
    Dim udtEstadoAnterior As EstadoSistemaDetalhado
    Dim udtMudancas As MudancasDetectadas
    Dim blnAnomalia As Boolean
    Dim udtTelLocal As Telemetria
    Dim dicItensAnteriores As Object
    Dim strTipoEfetivo As String
    Dim strDeltaHtml As String

    On Error GoTo TratarErro
        ProcessarNotificacoesCustomizadas = False

        GravarLogEx "Iniciando ProcessarNotificacoesCustomizadas (Plugin)", LOG_DEBUG

        Set dicItensAnteriores = CreateObject("Scripting.Dictionary")
        dicItensAnteriores.CompareMode = 1

        ' 1. Snapshot Do estado
        With udtEstadoAtual
            .dtmSnapshot = Now
            .lngTotalLinhas = lngTotalLinhas
            .lngTotalErros = lngTotalErros
            .strHashEstado = GerarHashEstadoAtual(lngTotalLinhas, lngTotalErros, arrErros)
        End With

        ' 2. Carregar cache e comparar delta
        udtEstadoAnterior = CarregarEstadoAnterior()
        CarregarItensEstadoAnterior dicItensAnteriores
        udtMudancas = CompararEstados(udtEstadoAtual, udtEstadoAnterior, arrErros, lngTotalErros, dicItensAnteriores)

        ' 3. Logica de anomalia
        blnAnomalia = (lngTotalErros >= LIMITE_ANOMALIA)
        If blnAnomalia Then
            GravarLogEx "ANOMALIA DETECTADA: Pico de erros (" & lngTotalErros & ")", LOG_WARNING
        End If

        ' 4. Persistencia (antes Do envio para evitar Loop)
        SalvarEstadoCache udtEstadoAtual
        SalvarItensEstadoCache arrErros, lngTotalErros

        strTipoEfetivo = udtMudancas.strTipoNotificacao
        If blnAnomalia And strTipoEfetivo = NOTIF_TIPO_NENHUMA And lngTotalErros > 0 Then
            strTipoEfetivo = NOTIF_TIPO_ERRO
            udtMudancas.blnHouveMudanca = True
        End If

        ' 5. Notificacao por mudanca de estado ou anomalia
        If udtMudancas.blnHouveMudanca Or blnAnomalia Then
            GravarLogEx "Mudanca de estado detectada. Disparando notificacao de e-mail.", LOG_INFO
            With udtTelLocal
                .totalLinhas = lngTotalLinhas
                .totalErros = lngTotalErros
                .InicioExecucao = Timer
            End With

            If strTipoEfetivo = NOTIF_TIPO_ALTERACAO Then
                strDeltaHtml = GerarResumoAlteracaoHtml(udtMudancas)
            Else
                strDeltaHtml = vbNullString
            End If

            On Error Resume Next
            modNotificacaoNF.FallbackNotificacaoPadrao udtTelLocal, arrErros, Nothing, strTipoEfetivo, _
            udtMudancas.lngTotalNovos, udtMudancas.lngTotalCorrigidos, udtMudancas.lngTotalPermanentes, strDeltaHtml
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
            ProcessarNotificacoesCustomizadas = False
End Function

' ====================================================================================
' INTERNOS / AUXILIARES
' ====================================================================================
Private Function GerarHashEstadoAtual(ByVal lngLinhas As Long, ByVal lngErros As Long, ByRef arr() As DadosErro) As String
    Dim lngI As Long
    Dim strBase As String
    Dim strResult As String

    ' Base estavel pelo contador - garante hash nao-vazio mesmo se array vazio
    strBase = CStr(lngLinhas) & "E" & CStr(lngErros) & ":"

    On Error Resume Next
    For lngI = 1 To lngErros
        strBase = strBase & GerarAssinaturaErro(arr(lngI)) & ";"
        If Len(strBase) > 5000 Then Exit For
        Next lngI
        On Error GoTo 0

            strResult = modUtil.GerarHashDJB2(strBase)
            If Len(strResult) = 0 Then strResult = CStr(lngErros) & "fallback"
                GerarHashEstadoAtual = strResult
End Function

Private Function CarregarEstadoAnterior() As EstadoSistemaDetalhado
    Dim udtEstado As EstadoSistemaDetalhado
    Dim intFileNum As Integer
    Dim strPath As String
    Dim strLinha As String
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

Private Function CompararEstados(ByRef udtAtual As EstadoSistemaDetalhado, ByRef udtAnterior As EstadoSistemaDetalhado, ByRef arrErrosAtuais() As DadosErro, ByVal lngTotalErrosAtuais As Long, ByVal dicItensAnteriores As Object) As MudancasDetectadas
    Dim udtMud As MudancasDetectadas
    Dim dicItensAtuais As Object
    Dim lngI As Long
    Dim strAssinatura As String
    Dim udtErro As DadosErro
    Dim varKey As Variant

    Set dicItensAtuais = CreateObject("Scripting.Dictionary")
    dicItensAtuais.CompareMode = 1

    For lngI = 1 To lngTotalErrosAtuais
        udtErro = arrErrosAtuais(lngI)
        strAssinatura = GerarAssinaturaErro(udtErro)
        dicItensAtuais(strAssinatura) = SerializarErroCacheLinha(strAssinatura, udtErro)

        If dicItensAnteriores.Exists(strAssinatura) Then
            AdicionarErroNoArray udtMud.arrPermanentes, udtMud.lngTotalPermanentes, udtErro
        Else
            AdicionarErroNoArray udtMud.arrNovos, udtMud.lngTotalNovos, udtErro
        End If
    Next lngI

    For Each varKey In dicItensAnteriores.Keys
        If Not dicItensAtuais.Exists(CStr(varKey)) Then
            udtErro = DesserializarErroCacheLinha(CStr(dicItensAnteriores(varKey)))
            AdicionarErroNoArray udtMud.arrCorrigidos, udtMud.lngTotalCorrigidos, udtErro
        End If
    Next varKey

    ' Sem estado anterior (primeira execucao ou cache apagado)
    If udtAnterior.dtmSnapshot = 0 Then
        If udtAtual.lngTotalErros > 0 Then
            udtMud.blnHouveMudanca = True
            udtMud.strTipoNotificacao = NOTIF_TIPO_ERRO
            GravarLogEx "Sem estado anterior: " & udtAtual.lngTotalErros & " erro(s) encontrado(s) - notificando.", LOG_INFO
        Else
            udtMud.strTipoNotificacao = NOTIF_TIPO_NENHUMA
        End If
        CompararEstados = udtMud
     Exit Function
    End If

    If udtAtual.lngTotalErros = 0 And udtAnterior.lngTotalErros > 0 Then
        udtMud.blnHouveMudanca = True
        udtMud.strTipoNotificacao = NOTIF_TIPO_ACERTO
    ElseIf udtAtual.lngTotalErros > 0 And udtAnterior.lngTotalErros = 0 Then
        udtMud.blnHouveMudanca = True
        udtMud.strTipoNotificacao = NOTIF_TIPO_ERRO
    ElseIf udtAtual.lngTotalErros > 0 And (udtMud.lngTotalNovos > 0 Or udtMud.lngTotalCorrigidos > 0) Then
        udtMud.blnHouveMudanca = True
        udtMud.strTipoNotificacao = NOTIF_TIPO_ALTERACAO
    ElseIf udtAtual.lngTotalErros <> udtAnterior.lngTotalErros Or udtAtual.strHashEstado <> udtAnterior.strHashEstado Then
        If udtAtual.lngTotalErros > 0 Then
            udtMud.blnHouveMudanca = True
            udtMud.strTipoNotificacao = NOTIF_TIPO_ALTERACAO
        Else
            udtMud.blnHouveMudanca = True
            udtMud.strTipoNotificacao = NOTIF_TIPO_ACERTO
        End If
    Else
        udtMud.strTipoNotificacao = NOTIF_TIPO_NENHUMA
        GravarLogEx "Estado inalterado: " & udtAtual.lngTotalErros & " erro(s). Sem notificacao.", LOG_DEBUG
    End If

    If udtMud.blnHouveMudanca Then
        GravarLogEx "Delta de estado: " & udtAnterior.lngTotalErros & " -> " & udtAtual.lngTotalErros & " erro(s). Hash: " & udtAnterior.strHashEstado & " -> " & udtAtual.strHashEstado, LOG_INFO
        GravarLogEx "Delta detalhado | Novos=" & udtMud.lngTotalNovos & " | Corrigidos=" & udtMud.lngTotalCorrigidos & " | Permanentes=" & udtMud.lngTotalPermanentes, LOG_INFO
    End If

    CompararEstados = udtMud
End Function

Private Sub CarregarItensEstadoAnterior(ByRef dicItens As Object)
    Dim intFileNum As Integer
    Dim strPath As String
    Dim strLinha As String
    Dim arrPartes() As String
    Dim strAssinatura As String

    On Error GoTo Falha

        strPath = ThisWorkbook.Path & "\" & CACHE_ITENS_FILE
        If Dir$(strPath) = vbNullString Then Exit Sub

            intFileNum = FreeFile
            Open strPath For Input As #intFileNum
            Do While Not EOF(intFileNum)
                Line Input #intFileNum, strLinha
                If Len(Trim$(strLinha)) > 0 Then
                    arrPartes = Split(strLinha, vbTab)
                    If UBound(arrPartes) >= 4 Then
                        strAssinatura = arrPartes(0)
                        If Len(strAssinatura) > 0 Then
                            dicItens(strAssinatura) = strLinha
                        End If
                    End If
                End If
            Loop
            Close #intFileNum
         Exit Sub

Falha:
            On Error Resume Next
            If intFileNum > 0 Then Close #intFileNum
                GravarLogEx "Erro ao carregar cache de itens: " & Err.Description, LOG_WARNING
End Sub

Private Sub SalvarItensEstadoCache(ByRef arrErros() As DadosErro, ByVal lngTotalErros As Long)
    Dim intFileNum As Integer
    Dim strPath As String
    Dim lngI As Long
    Dim strAssinatura As String

    On Error GoTo Falha

        strPath = ThisWorkbook.Path & "\" & CACHE_ITENS_FILE
        intFileNum = FreeFile

        Open strPath For Output As #intFileNum
        For lngI = 1 To lngTotalErros
            strAssinatura = GerarAssinaturaErro(arrErros(lngI))
            Print #intFileNum, SerializarErroCacheLinha(strAssinatura, arrErros(lngI))
        Next lngI
        Close #intFileNum

        GravarLogEx "Cache de itens atualizado: " & strPath, LOG_DEBUG
     Exit Sub

Falha:
        On Error Resume Next
        If intFileNum > 0 Then Close #intFileNum
            GravarLogEx "Erro ao salvar cache de itens: " & Err.Description, LOG_WARNING
End Sub

Private Function SerializarErroCacheLinha(ByVal strAssinatura As String, ByRef udtErro As DadosErro) As String
    SerializarErroCacheLinha = strAssinatura & vbTab & _
    SanitizarCacheCampo(CStr(udtErro.NumOB)) & vbTab & _
    SanitizarCacheCampo(CStr(udtErro.Progr)) & vbTab & _
    SanitizarCacheCampo(CStr(udtErro.refCliente)) & vbTab & _
    SanitizarCacheCampo(CStr(udtErro.detalheErro))
End Function

Private Function DesserializarErroCacheLinha(ByVal strLinha As String) As DadosErro
    Dim udtErro As DadosErro
    Dim arrPartes() As String

    arrPartes = Split(strLinha, vbTab)
    If UBound(arrPartes) >= 4 Then
        udtErro.NumOB = arrPartes(1)
        udtErro.Progr = arrPartes(2)
        udtErro.refCliente = arrPartes(3)
        udtErro.detalheErro = arrPartes(4)
    End If

    DesserializarErroCacheLinha = udtErro
End Function

Private Function GerarAssinaturaErro(ByRef udtErro As DadosErro) As String
    Dim strBase As String
    Dim strHash As String

    strBase = UCase$(Trim$(CStr(udtErro.NumOB))) & "|" & _
    UCase$(Trim$(CStr(udtErro.Progr))) & "|" & _
    UCase$(Trim$(CStr(udtErro.refCliente))) & "|" & _
    UCase$(Trim$(CStr(udtErro.detalheErro)))

    If Len(strBase) = 0 Then strBase = "VAZIO"

        strHash = modUtil.GerarHashDJB2(strBase)
        If Len(strHash) = 0 Then strHash = strBase
            GerarAssinaturaErro = strHash
End Function

Private Sub AdicionarErroNoArray(ByRef arrErros() As DadosErro, ByRef lngTotal As Long, ByRef udtErro As DadosErro)
    lngTotal = lngTotal + 1

    If lngTotal = 1 Then
        ReDim arrErros(1 To 1)
    Else
        ReDim Preserve arrErros(1 To lngTotal)
    End If

    arrErros(lngTotal) = udtErro
End Sub

Private Function GerarResumoAlteracaoHtml(ByRef udtMudancas As MudancasDetectadas) As String
    Dim strHtml As String

    strHtml = "<p style='font-size:11pt;margin:0 0 10px 0;'><b>Resumo detalhado da alteracao:</b></p>"
    strHtml = strHtml & "<table border='0' cellspacing='0' cellpadding='6' style='border-collapse:collapse;font-family:Calibri,Arial,sans-serif;font-size:10pt;margin-bottom:14px;'>"
    strHtml = strHtml & "<tr><td style='background:#fdecec;'><b>Novos:</b> " & CStr(udtMudancas.lngTotalNovos) & "</td><td style='background:#ecfdf3;'><b>Corrigidos:</b> " & CStr(udtMudancas.lngTotalCorrigidos) & "</td><td style='background:#fff7ed;'><b>Permanentes:</b> " & CStr(udtMudancas.lngTotalPermanentes) & "</td></tr>"
    strHtml = strHtml & "</table>"

    strHtml = strHtml & GerarTabelaCategoriaHtml("Novos", udtMudancas.arrNovos, udtMudancas.lngTotalNovos, "#b91c1c")
    strHtml = strHtml & GerarTabelaCategoriaHtml("Corrigidos", udtMudancas.arrCorrigidos, udtMudancas.lngTotalCorrigidos, "#166534")
    strHtml = strHtml & GerarTabelaCategoriaHtml("Permanentes", udtMudancas.arrPermanentes, udtMudancas.lngTotalPermanentes, "#92400e")

    GerarResumoAlteracaoHtml = strHtml
End Function

Private Function GerarTabelaCategoriaHtml(ByVal strTitulo As String, ByRef arrErros() As DadosErro, ByVal lngTotal As Long, ByVal strCorTitulo As String) As String
    Dim strHtml As String
    Dim lngI As Long

    strHtml = "<p style='font-size:10pt;margin:10px 0 6px 0;color:" & strCorTitulo & ";'><b>" & HTMLEncode(strTitulo) & " (" & CStr(lngTotal) & ")</b></p>"

    If lngTotal < 1 Then
        GerarTabelaCategoriaHtml = strHtml & "<p style='font-size:9pt;color:#666;margin:0 0 8px 0;'><i>Sem itens neste grupo.</i></p>"
     Exit Function
    End If

    strHtml = strHtml & "<table border='1' cellspacing='0' cellpadding='5' style='border-collapse:collapse;font-family:Calibri,Arial,sans-serif;font-size:9pt;width:100%;margin-bottom:10px;'>"
    strHtml = strHtml & "<tr style='background:#f3f4f6;'><th>Num OB</th><th>Ref Cliente</th><th>Progr</th><th>Detalhe Erro</th></tr>"

    For lngI = 1 To lngTotal
        strHtml = strHtml & "<tr>"
        strHtml = strHtml & "<td>" & HTMLEncode(CStr(arrErros(lngI).NumOB)) & "</td>"
        strHtml = strHtml & "<td>" & HTMLEncode(CStr(arrErros(lngI).refCliente)) & "</td>"
        strHtml = strHtml & "<td>" & HTMLEncode(CStr(arrErros(lngI).Progr)) & "</td>"
        strHtml = strHtml & "<td>" & HTMLEncode(CStr(arrErros(lngI).detalheErro)) & "</td>"
        strHtml = strHtml & "</tr>"
    Next lngI

    strHtml = strHtml & "</table>"
    GerarTabelaCategoriaHtml = strHtml
End Function

Private Sub SalvarEstadoCache(ByRef udtEstado As EstadoSistemaDetalhado)
    Dim intFileNum As Integer
    Dim strPath As String
    Dim strLinha As String

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
        On Error Resume Next
        If intFileNum > 0 Then Close #intFileNum
            GravarLogEx "Erro ao salvar cache: " & Err.Description, LOG_WARNING
End Sub

Private Function HTMLEncode(ByVal strIn As String) As String
    strIn = Replace(strIn, "&", "&amp;")
    strIn = Replace(strIn, "<", "&lt;")
    strIn = Replace(strIn, ">", "&gt;")
    strIn = Replace(strIn, """", "&quot;")
    strIn = Replace(strIn, "'", "&#39;")
    HTMLEncode = strIn
End Function

Private Function SanitizarCacheCampo(ByVal strIn As String) As String
    strIn = Replace(strIn, vbTab, " ")
    strIn = Replace(strIn, vbCr, " ")
    strIn = Replace(strIn, vbLf, " ")
    SanitizarCacheCampo = Trim$(strIn)
End Function

' VUL-09: GerarHashDJB2 removida deste modulo.
' Uso centralizado em modUtil.GerarHashDJB2 (canonica, ASCII-safe, Hex output).
