Attribute VB_Name = "modValidacaoNF"
Option Explicit

Private m_objRegexNF As Object  ' VBScript.RegExp (late binding)

' ====================================================================================
' ENTRY POINT (Public)
' ====================================================================================
Public Sub ValidarNotasFiscais(ByRef udtTel As Telemetria, _
    Optional ByVal blnSilencioso As Boolean = False, _
    Optional ByVal blnGerenciarConfig As Boolean = True, _
    Optional ByVal objWsAlvo As Worksheet = Nothing)
    Dim objWsTrabalho  As Worksheet
    Dim blnSucesso     As Boolean

    On Error GoTo TratarErro

        ' 1. Resolucao da Worksheet (Elimina ActiveSheet)
        If objWsAlvo Is Nothing Then
            Set objWsTrabalho = ActiveSheet
        Else
            Set objWsTrabalho = objWsAlvo
        End If

        If objWsTrabalho Is Nothing Then
            Err.Raise vbObjectError + 601, "modValidacaoNF", "Nenhuma Worksheet definida para validacao."
        End If

        GravarLogEx "ValidarNotasFiscais | Planilha=" & objWsTrabalho.Name & " | Silencioso=" & blnSilencioso, LOG_DEBUG

        ' 2. Execucao
        blnSucesso = ExecutarValidacaoCompleta(objWsTrabalho, udtTel, blnSilencioso)

        If Not blnSucesso Then
            GravarLogEx "AVISO: ExecutarValidacaoCompleta retornou False.", LOG_WARNING
        End If

SaidaLimpa:
        If Not blnSilencioso Then Application.StatusBar = False
            GravarLogEx "ValidarNotasFiscais finalizado.", LOG_DEBUG
         Exit Sub

TratarErro:
            Dim strErro As String
            strErro = "ERRO em ValidarNotasFiscais: " & Err.Description
            GravarLogEx strErro, LOG_ERROR
            If Not blnSilencioso Then MsgBox strErro, vbCritical
                Resume SaidaLimpa
End Sub

' ====================================================================================
' CORE
' ====================================================================================
Private Function ExecutarValidacaoCompleta(ByVal objWs As Worksheet, ByRef udtTel As Telemetria, ByVal blnSilencioso As Boolean) As Boolean
    Dim objTblPrincipal   As ListObject
    Dim rngCabecalho      As Range
    Dim dicColunas        As Object  ' Scripting.Dictionary (late binding)
    Dim varDadosArray     As Variant
    Dim arrErros()        As DadosErro
    Dim varArrAlternativo As Variant
    Dim blnTemAlternativo As Boolean
    Dim lngI              As Long
    Dim lngTotalErros     As Long
    Dim lngIdxColVal      As Long
    Dim lngLinhaInicial   As Long
    Dim lngColStart       As Long
    Dim dblPercentual     As Double

    On Error GoTo ErroValidacao
        ExecutarValidacaoCompleta = False
        GravarLogEx "ExecutarValidacaoCompleta iniciado na aba: " & objWs.Name, LOG_DEBUG

        InicializarRegex

        If objWs.ListObjects.count = 0 Then
            Err.Raise vbObjectError + 602, "ExecutarValidacaoCompleta", "Nenhuma tabela encontrada na aba " & objWs.Name
        End If

        Set objTblPrincipal = objWs.ListObjects(1)
        If objTblPrincipal.ListRows.count < 1 Or objTblPrincipal.DataBodyRange Is Nothing Then
            GravarLogEx "AVISO: Tabela vazia (" & objTblPrincipal.Name & ").", LOG_WARNING
            If Not blnSilencioso Then MsgBox "Tabela vazia.", vbExclamation
                ExecutarValidacaoCompleta = True ' Nao e erro fatal, apenas nada a fazer
             Exit Function
            End If

            Set rngCabecalho = objTblPrincipal.HeaderRowRange
            lngLinhaInicial = objTblPrincipal.DataBodyRange.Row
            lngColStart = objTblPrincipal.Range.Column

            Set dicColunas = CreateObject("Scripting.Dictionary")
            dicColunas.CompareMode = 1

            Dim objCel As Range, strNomeCol As String
            For Each objCel In rngCabecalho.Cells
                strNomeCol = Trim$(CStr(objCel.Value))
                If Len(strNomeCol) > 0 Then dicColunas(strNomeCol) = objCel.Column
                Next objCel

                ' Validacao de Colunas Obrigatorias
                If Not (dicColunas.Exists(C_REF_CLIENTE) And dicColunas.Exists(C_QT_PC_NF) And _
                    dicColunas.Exists(C_OBS_OB) And dicColunas.Exists(C_OUTPUT_VAL)) Then
                    Err.Raise vbObjectError + 603, "ExecutarValidacaoCompleta", "Colunas obrigatorias ausentes."
                End If

                lngIdxColVal = CLng(dicColunas(C_OUTPUT_VAL))

                ' Limpeza previa (Protegido contra Nothing)
                Dim rngLimpeza As Range
                Set rngLimpeza = Intersect(objTblPrincipal.DataBodyRange, objWs.Columns(lngIdxColVal))

                If Not rngLimpeza Is Nothing Then
                    With rngLimpeza
                        .ClearContents
                        .Interior.ColorIndex = xlNone
                    End With
                End If

                blnTemAlternativo = dicColunas.Exists(C_ALTERNATIVO)
                If blnTemAlternativo Then
                    On Error Resume Next
                    varArrAlternativo = objWs.Range( _
                    objWs.Cells(lngLinhaInicial, CLng(dicColunas(C_ALTERNATIVO))), _
                    objWs.Cells(lngLinhaInicial + objTblPrincipal.ListRows.count - 1, CLng(dicColunas(C_ALTERNATIVO)))).Value2
                    If Err.Number <> 0 Then blnTemAlternativo = False
                        On Error GoTo ErroValidacao
                        End If

                        varDadosArray = objTblPrincipal.DataBodyRange.Value2
                        ReDim arrErros(1 To UBound(varDadosArray, 1))
                        udtTel.totalLinhas = CLng(UBound(varDadosArray, 1))
                        lngTotalErros = 0

                        Dim strRefCliente     As String
                        Dim strNfObsOB        As String
                        Dim blnMontagemOk     As Boolean
                        Dim blnProgErro       As Boolean
                        Dim strDetalheErro    As String
                        Dim objCelVal         As Range

                        For lngI = 1 To UBound(varDadosArray, 1)

                            If Not blnSilencioso Then
                                HandleUserInterruption lngI, UBound(varDadosArray, 1)
                            End If

                            strRefCliente = Trim$(CStr(varDadosArray(lngI, CLng(dicColunas(C_REF_CLIENTE)) - lngColStart + 1)))
                            blnMontagemOk = ValidarMultiplosNFs(CStr(varDadosArray(lngI, CLng(dicColunas(C_QT_PC_NF)) - lngColStart + 1)), strRefCliente)
                            strNfObsOB = ExtrairNFPosNF(CStr(varDadosArray(lngI, CLng(dicColunas(C_OBS_OB)) - lngColStart + 1)))
                            blnProgErro = (strRefCliente <> strNfObsOB)

                            strDetalheErro = ""
                            If (Not blnMontagemOk) And blnProgErro Then strDetalheErro = "Erro de Montagem e Programacao"
                                If (Not blnMontagemOk) And (Not blnProgErro) Then strDetalheErro = "Erro de Montagem"
                                    If blnMontagemOk And blnProgErro Then strDetalheErro = "Erro de Programacao"

                                        Set objCelVal = objWs.Cells(lngLinhaInicial + lngI - 1, lngIdxColVal)

                                        If Len(strDetalheErro) > 0 Then
                                            lngTotalErros = lngTotalErros + 1
                                            objCelVal.Value = strDetalheErro
                                            objCelVal.Interior.Color = RGB(255, 199, 206)

                                            PreencherEstruturaErro arrErros(lngTotalErros), varDadosArray, lngI, lngColStart, dicColunas, strRefCliente, strNfObsOB, strDetalheErro, varArrAlternativo, blnTemAlternativo
                                        Else
                                            objCelVal.Value = "OK"
                                            objCelVal.Interior.ColorIndex = xlNone
                                        End If
                                    Next lngI

                                    udtTel.totalErros = lngTotalErros
                                    GravarLogEx "Validacao concluida | Erros=" & lngTotalErros, LOG_INFO

                                    ' Notificacoes
                                    LogStepStart "NOTIF"
                                    If Not ProcessarNotificacoesWrapper(udtTel, arrErros, blnSilencioso) Then
                                        GravarLogEx "AVISO: Notificacoes customizadas falharam. Usando fallback.", LOG_WARNING
                                        FallbackNotificacaoPadrao udtTel, arrErros, objWs
                                    End If
                                    LogStepEnd "OK"

                                    ExecutarValidacaoCompleta = True
                                 Exit Function

ErroValidacao:
                                    GravarLogEx "ERRO validacao: " & Err.Description & " | Linha=" & Erl, LOG_ERROR
                                    ExecutarValidacaoCompleta = False
End Function

' ====================================================================================
' AUXILIARES DE LOGICA
' ====================================================================================

Private Sub HandleUserInterruption(ByVal lngAtual As Long, ByVal lngTotal As Long)
    If (lngAtual Mod 100) = 0 Then
        If GetAsyncKeyState(vbKeyEscape) <> 0 Then
            If MsgBox("Deseja interromper o processamento?", vbYesNo + vbQuestion, "Interrupcao") = vbYes Then
                Err.Raise vbObjectError + 999, "modValidacaoNF", "Cancelado pelo usuario."
            End If
        End If
    End If
    If (lngAtual Mod 1000) = 0 Then
        Dim dblPercentual As Double
        dblPercentual = 50 + (CDbl(lngAtual) / CDbl(lngTotal)) * 40
        Application.StatusBar = ">> [" & Format$(dblPercentual, "0") & "%] Processando linha " & lngAtual & " de " & lngTotal
        DoEvents
    End If
End Sub

Private Sub PreencherEstruturaErro(ByRef udtErro As DadosErro, ByVal varDados As Variant, ByVal lngI As Long, ByVal lngColStart As Long, ByVal dicCol As Object, ByVal strRef As String, ByVal strObs As String, ByVal strDet As String, ByVal varAlt As Variant, ByVal blnAlt As Boolean)
    With udtErro
        If dicCol.Exists(C_SIT_OB) Then .SitOB = varDados(lngI, CLng(dicCol(C_SIT_OB)) - lngColStart + 1)
            If dicCol.Exists(C_PROGR) Then .Progr = varDados(lngI, CLng(dicCol(C_PROGR)) - lngColStart + 1)
                If dicCol.Exists(C_FACCAO) Then .Faccao = varDados(lngI, CLng(dicCol(C_FACCAO)) - lngColStart + 1)
                    If dicCol.Exists(C_PCS_PROG) Then .pcsProg = varDados(lngI, CLng(dicCol(C_PCS_PROG)) - lngColStart + 1)
                        If dicCol.Exists(C_NUM_OB) Then .NumOB = varDados(lngI, CLng(dicCol(C_NUM_OB)) - lngColStart + 1)
                            If dicCol.Exists(C_KANBAN) Then .Kanban = varDados(lngI, CLng(dicCol(C_KANBAN)) - lngColStart + 1)
                                If dicCol.Exists(C_FASE_ATUAL) Then .FaseAtual = varDados(lngI, CLng(dicCol(C_FASE_ATUAL)) - lngColStart + 1)
                                    If dicCol.Exists(C_ST_FASE) Then .StatusFase = varDados(lngI, CLng(dicCol(C_ST_FASE)) - lngColStart + 1)
                                        If dicCol.Exists(C_DT_ULT_CONF) Then .DtUltConf = varDados(lngI, CLng(dicCol(C_DT_ULT_CONF)) - lngColStart + 1)
                                            .refCliente = strRef
                                            .qtpcnf = CStr(varDados(lngI, CLng(dicCol(C_QT_PC_NF)) - lngColStart + 1))
                                            .ObsOB = strObs
                                            .detalheErro = strDet
                                            If blnAlt Then
                                                .Alternativo = Trim$(CStr(varAlt(lngI, 1)))
                                            Else
                                                .Alternativo = ""
                                            End If
                                        End With
End Sub

' ====================================================================================
' REGEX / PARSING
' ====================================================================================
Private Sub InicializarRegex()
    If m_objRegexNF Is Nothing Then
        Set m_objRegexNF = CreateObject("VBScript.RegExp")
        With m_objRegexNF
            .Pattern = "NF:\s*(\d+)"
            .Global = False
            .IgnoreCase = True
        End With
    End If
End Sub

Private Function ValidarMultiplosNFs(ByVal strTexto As String, ByVal strRefCliente As String) As Boolean
    Dim arrPartes()    As String
    Dim varParte       As Variant
    Dim arrSubPartes() As String
    Dim strNfAtual     As String

    ValidarMultiplosNFs = True
    If Len(Trim$(strTexto)) = 0 Then Exit Function

        arrPartes = Split(strTexto, ",")
        For Each varParte In arrPartes
            arrSubPartes = Split(CStr(varParte), "-")
            If UBound(arrSubPartes) >= 1 Then
                strNfAtual = Trim$(CStr(arrSubPartes(1)))
                If strNfAtual <> strRefCliente Then
                    ValidarMultiplosNFs = False: Exit Function
                End If
            End If
        Next varParte
End Function

Private Function ExtrairNFPosNF(ByVal strTexto As String) As String
    InicializarRegex
    If m_objRegexNF.Test(strTexto) Then
        ExtrairNFPosNF = CStr(m_objRegexNF.Execute(strTexto)(0).SubMatches(0))
    Else
        ExtrairNFPosNF = ""
    End If
End Function
