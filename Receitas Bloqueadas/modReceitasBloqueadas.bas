Attribute VB_Name = "modReceitasBloqueadas"
Option Explicit

Private m_execId As String
Private m_blnInLogWrite As Boolean
Private m_outlookAdapter As ClsRBOutlookAdapter

Private Const LOG_BASE_FOLDER As String = "C:\Automacoes\Receitas Bloqueadas\Logs"
Private Const NOME_TABELA_DADOS As String = "ReceitasBloqueadas"
Private Const NOME_TABELA_EMAIL As String = "EnderecosEmailDestinatarios"
Private Const ABA_CONFIG As String = "Config"
Private Const ABA_DADOS As String = "ReceitasBloqueadas"

Private Const NOME_CONEXAO_DADOS As String = "Consulta - ReceitasBloqueadas"
Private Const NOME_CONEXAO_OBS As String = "Consulta - OBsReceitasBloqueadas"

Private Const OL_MAIL_ITEM As Long = 0
Private Const VB_MINIMIZED_FOCUS As Long = 2

Private Function ObterCaminhoLog() As String
    ObterCaminhoLog = LOG_BASE_FOLDER & "\ReceitasBloqueadas.log"
End Function

Public Sub ExecutarProcessoCompleto(Optional ByVal execId As String = "")
    Dim corpoHTML As String

    m_execId = NormalizeExecId(execId)

    On Error GoTo TratarErro

    RegistrarLog "INICIO - Processo VBA iniciado"
    RegistrarLog "Atualizando conexoes"

    AtualizarConexaoComGarantia NOME_CONEXAO_DADOS
    AtualizarConexaoComGarantia NOME_CONEXAO_OBS

    Application.Wait Now + TimeValue("0:00:02")

    AjustarFormatoDatasReceitasBloqueadas

    ThisWorkbook.Save
    RegistrarLog "Workbook salvo"

    corpoHTML = GerarHTMLDinamico()

    If Len(corpoHTML) = 0 Then
        RegistrarLog "AVISO: Tabela vazia ou n" & ChrW$(227) & "o encontrada. E-mail cancelado"
        RegistrarLog "FIM DO PROCESSO. Resultado=Sem envio"
        Exit Sub
    End If

    RegistrarLog "Enviando e-mail"
    EnviarEmailOutlook corpoHTML

    RegistrarLog "FIM DO PROCESSO. Resultado=Sucesso"
    Exit Sub

TratarErro:
    RegistrarLog "ERRO FATAL: " & Err.Description & " (" & CStr(Err.Number) & ")"
    RegistrarLog "FIM DO PROCESSO. Resultado=Erro"
End Sub

Public Sub PreVisualizarEmail()
    Dim corpoHTML As String

    m_execId = NormalizeExecId("PREVIEW_" & Format$(Now, "yyyymmdd_hhnnss"))

    On Error GoTo TratarErro

    RegistrarLog "INICIO - Pre-visualizacao do email iniciada"
    RegistrarLog "Atualizando conexoes"

    AtualizarConexaoComGarantia NOME_CONEXAO_DADOS
    AtualizarConexaoComGarantia NOME_CONEXAO_OBS

    Application.Wait Now + TimeValue("0:00:02")

    AjustarFormatoDatasReceitasBloqueadas

    ThisWorkbook.Save
    RegistrarLog "Workbook salvo"

    corpoHTML = GerarHTMLDinamico()

    If Len(corpoHTML) = 0 Then
        RegistrarLog "AVISO: Tabela vazia ou n" & ChrW$(227) & "o encontrada. Pr" & ChrW$(233) & "-visualiza" & ChrW$(231) & ChrW$(227) & "o cancelada"
        Exit Sub
    End If

    RegistrarLog "Abrindo pre-visualizacao do email"
    EnviarEmailOutlook corpoHTML, True
    RegistrarLog "Pre-visualizacao exibida com sucesso"
    Exit Sub

TratarErro:
    RegistrarLog "ERRO FATAL na pre-visualizacao: " & Err.Description & " (" & CStr(Err.Number) & ")"
End Sub

Private Sub AtualizarConexaoComGarantia(ByVal nomeConexao As String)
    Dim conn As workbookConnection

    On Error GoTo TratarErro

    Set conn = Nothing

    On Error Resume Next
    Set conn = ThisWorkbook.Connections(nomeConexao)
    On Error GoTo TratarErro

    If conn Is Nothing Then
        RegistrarLog "ERRO: Conex" & ChrW$(227) & "o '" & nomeConexao & "' n" & ChrW$(227) & "o encontrada"
        Exit Sub
    End If

    Select Case conn.Type
        Case xlConnectionTypeOLEDB
            conn.OLEDBConnection.BackgroundQuery = False
        Case xlConnectionTypeODBC
            conn.ODBCConnection.BackgroundQuery = False
    End Select

    conn.Refresh
    RegistrarLog "SUCESSO: Conexao '" & nomeConexao & "' atualizada"
    Exit Sub

TratarErro:
    RegistrarLog "FALHA ao atualizar '" & nomeConexao & "': " & Err.Description & " (" & CStr(Err.Number) & ")"
End Sub

Private Sub AjustarFormatoDatasReceitasBloqueadas()
    Dim ws As Worksheet
    Dim lo As ListObject

    On Error GoTo TratarErro

    Set ws = ThisWorkbook.Worksheets(ABA_DADOS)
    Set lo = ObterTabela(ws, NOME_TABELA_DADOS)

    If lo Is Nothing Then
        RegistrarLog "AVISO: Tabela '" & NOME_TABELA_DADOS & "' n" & ChrW$(227) & "o encontrada para formata" & ChrW$(231) & ChrW$(227) & "o"
        Exit Sub
    End If

    If lo.DataBodyRange Is Nothing Then
        RegistrarLog "AVISO: Tabela '" & NOME_TABELA_DADOS & "' sem linhas para formatacao"
        Exit Sub
    End If

    AplicarFormatoColunaData lo, NomeColunaDataUltimaProd()
    AplicarFormatoColunaData lo, NomeColunaDataBloqueio()
    AplicarFormatoColunaData lo, NomeColunaPrevisaoLiberar()

    Exit Sub

TratarErro:
    RegistrarLog "ERRO ao formatar datas da tabela: " & Err.Description & " (" & CStr(Err.Number) & ")"
End Sub

Private Sub AplicarFormatoColunaData(ByVal lo As ListObject, ByVal nomeColuna As String)
    Dim lc As ListColumn

    On Error GoTo TratarErro

    Set lc = ObterListColumn(lo, nomeColuna)

    If lc Is Nothing Then
        RegistrarLog "AVISO: Coluna '" & nomeColuna & "' n" & ChrW$(227) & "o encontrada"
        Exit Sub
    End If

    If lc.DataBodyRange Is Nothing Then
        RegistrarLog "AVISO: Coluna '" & nomeColuna & "' sem dados para formatacao"
        Exit Sub
    End If

    lc.DataBodyRange.NumberFormat = "dd/mm/yyyy"
    RegistrarLog "Formato PT-BR aplicado na coluna '" & nomeColuna & "'"

    Exit Sub

TratarErro:
    RegistrarLog "ERRO ao aplicar formato na coluna '" & nomeColuna & "': " & Err.Description & " (" & CStr(Err.Number) & ")"
End Sub

Private Function GerarHTMLDinamico() As String
    Dim ws As Worksheet
    Dim lo As ListObject
    Dim html As String
    Dim i As Long
    Dim j As Long
    Dim nomeColuna As String
    Dim textoCelula As String
    Dim corLinha As String

    On Error GoTo TratarErro

    Set ws = ThisWorkbook.Worksheets(ABA_DADOS)
    Set lo = ObterTabela(ws, NOME_TABELA_DADOS)

    If lo Is Nothing Then Exit Function
    If lo.DataBodyRange Is Nothing Then Exit Function

    html = ""

    html = html & "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;font-family:Segoe UI,Calibri,Arial,sans-serif;font-size:11pt;color:#1f2937;'>"
    html = html & "<tr>"
    html = html & "<td align='center' style='padding:0;'>"

    html = html & "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;max-width:1100px;border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;'>"

    html = html & "<tr>"
        html = html & "<td align='center' style='background:#0f4c81;color:#ffffff;padding:18px 22px 14px 22px;text-align:center;'>"

    html = html & "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;'>"
    html = html & "<tr>"
        html = html & "<td align='center' style='text-align:center;font-size:17pt;font-weight:bold;line-height:1.25;padding:0 0 8px 0;color:#ffffff;'>"
    html = html & HtmlEncode(TextoEmailTitulo())
    html = html & "</td>"
    html = html & "</tr>"

    html = html & "<tr>"
        html = html & "<td align='center' style='text-align:center;font-size:10.5pt;line-height:1.5;padding:0;color:#e8f1ff;'>"
    html = html & HtmlEncode(TextoEmailIntro()) & Format$(Now, "dd/MM/yyyy HH:mm")
    html = html & "</td>"
    html = html & "</tr>"
    html = html & "</table>"

    html = html & "</td>"
    html = html & "</tr>"

    html = html & "<tr>"
    html = html & "<td style='border:1px solid #d1d5db;border-top:none;padding:16px;'>"

    html = html & "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;font-size:10pt;'>"

    html = html & "<tr>"
    For i = 1 To lo.ListColumns.Count
        html = html & "<th style='background:#e5eef8;border:1px solid #cbd5e1;text-align:center;font-weight:bold;padding:6px;'>"
        html = html & HtmlEncode(CStr(lo.HeaderRowRange.Cells(1, i).Value))
        html = html & "</th>"
    Next i
    html = html & "</tr>"

    For i = 1 To lo.ListRows.Count
        If (i Mod 2) = 0 Then
            corLinha = "#f8fafc"
        Else
            corLinha = "#ffffff"
        End If

        html = html & "<tr>"

        For j = 1 To lo.ListColumns.Count
            nomeColuna = CStr(lo.HeaderRowRange.Cells(1, j).Value)
            textoCelula = ObterTextoCelula(lo.DataBodyRange.Cells(i, j), nomeColuna)

            html = html & "<td style='border:1px solid #dbe3ee;text-align:center;background:" & corLinha & ";padding:6px;'>"
            html = html & HtmlEncode(textoCelula)
            html = html & "</td>"
        Next j

        html = html & "</tr>"
    Next i

    html = html & "</table>"

    html = html & "<table role='presentation' cellspacing='0' cellpadding='0' border='0' width='100%' style='width:100%;border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;'>"
    html = html & "<tr>"
    html = html & "<td style='padding-top:14px;color:#b91c1c;font-weight:bold;'>"
    html = html & HtmlEncode(TextoEmailRodape())
    html = html & "</td>"
    html = html & "</tr>"
    html = html & "</table>"

    html = html & "</td>"
    html = html & "</tr>"

    html = html & "</table>"

    html = html & "</td>"
    html = html & "</tr>"
    html = html & "</table>"

    GerarHTMLDinamico = html
    Exit Function

TratarErro:
    RegistrarLog "ERRO ao gerar HTML: " & Err.Description & " (" & CStr(Err.Number) & ")"
    GerarHTMLDinamico = vbNullString
End Function

Private Function ObterTextoCelula(ByVal cel As Range, ByVal nomeColuna As String) As String
    Dim valorCelula As Variant

    On Error GoTo TratarErro

    valorCelula = cel.Value

    If IsError(valorCelula) Then
        ObterTextoCelula = Trim$(CStr(cel.Text))
        Exit Function
    End If

    If EhColunaData(nomeColuna) Then
        If IsDate(valorCelula) Then
            ObterTextoCelula = Format$(CDate(valorCelula), "dd/MM/yyyy")
        Else
            ObterTextoCelula = Trim$(CStr(cel.Text))
        End If
    Else
        If VarType(valorCelula) = vbDate Then
            ObterTextoCelula = Format$(CDate(valorCelula), "dd/MM/yyyy")
        Else
            ObterTextoCelula = Trim$(CStr(cel.Text))
        End If
    End If

    Exit Function

TratarErro:
    ObterTextoCelula = Trim$(CStr(cel.Text))
End Function

Private Function EhColunaData(ByVal nomeColuna As String) As Boolean
    Dim nomeNormalizado As String

    nomeNormalizado = UCase$(Trim$(nomeColuna))

    Select Case nomeNormalizado
        Case UCase$(NomeColunaDataUltimaProd()), _
             UCase$(NomeColunaDataBloqueio()), _
             UCase$(NomeColunaPrevisaoLiberar())
            EhColunaData = True
        Case Else
            EhColunaData = False
    End Select
End Function

Private Function HtmlEncode(ByVal texto As String) As String
    texto = Replace(texto, "&", "&amp;")
    texto = Replace(texto, "<", "&lt;")
    texto = Replace(texto, ">", "&gt;")
    texto = Replace(texto, """", "&quot;")
    texto = Replace(texto, "'", "&#39;")
    HtmlEncode = texto
End Function

Private Sub EnviarEmailOutlook(ByVal htmlBody As String, Optional ByVal previewOnly As Boolean = False)
    Dim sPara As String
    Dim sCopia As String
    Dim sCco As String
    Dim strIntro As String
    Dim strLegenda As String
    Dim outlookAdapter As ClsRBOutlookAdapter

    On Error GoTo TratarErro

    ObterDestinatariosEmail sPara, sCopia, sCco

    If Len(sPara) = 0 Then
        RegistrarLog "ERRO: Destinat" & ChrW$(225) & "rio principal n" & ChrW$(227) & "o informado"
        Exit Sub
    End If

    strIntro = "Segue relat" & ChrW$(243) & "rio atualizado de receitas bloqueadas."
    strLegenda = HtmlEncode(TextoEmailAssinatura())

    Set outlookAdapter = GetOutlookAdapter()
    RegistrarLog "Definindo assunto e destinatarios"

    If Not outlookAdapter.EnviarEmail(sPara, sCopia, sCco, TextoEmailAssuntoPrefixo() & Format$(Date, "dd/MM/yyyy"), htmlBody, strIntro, strLegenda, previewOnly) Then
        Err.Raise vbObjectError + 5101, "EnviarEmailOutlook", outlookAdapter.LastError
    End If

    If previewOnly Then
        RegistrarLog "E-mail exibido em pre-visualizacao"
    Else
        RegistrarLog "E-mail enviado com sucesso"
    End If
Saida:
    Set outlookAdapter = Nothing
    Exit Sub

TratarErro:
    RegistrarLog "ERRO no envio do e-mail: " & Err.Description & " (" & CStr(Err.Number) & ")"
    Resume Saida
End Sub

Private Function GetOutlookAdapter() As ClsRBOutlookAdapter
    If m_outlookAdapter Is Nothing Then
        Set m_outlookAdapter = New ClsRBOutlookAdapter
    End If

    Set GetOutlookAdapter = m_outlookAdapter
End Function

Private Sub ObterDestinatariosEmail(ByRef sPara As String, ByRef sCopia As String, ByRef sCco As String)
    Dim wsC As Worksheet
    Dim tblE As ListObject
    Dim idxPara As Long
    Dim idxCopia As Long
    Dim idxCco As Long

    sPara = vbNullString
    sCopia = vbNullString
    sCco = vbNullString

    On Error GoTo TratarErro

    Set wsC = ThisWorkbook.Worksheets(ABA_CONFIG)
    Set tblE = ObterTabela(wsC, NOME_TABELA_EMAIL)

    If tblE Is Nothing Then
        RegistrarLog "ERRO: Tabela de destinat" & ChrW$(225) & "rios '" & NOME_TABELA_EMAIL & "' n" & ChrW$(227) & "o encontrada"
        Exit Sub
    End If

    If tblE.DataBodyRange Is Nothing Then
        RegistrarLog "ERRO: Tabela de destinatarios sem dados"
        Exit Sub
    End If

    idxPara = ObterIndiceColunaPorSinonimos(tblE, Array("PARA", "TO", "DESTINATARIO", "DESTINATARIO PRINCIPAL", "EMAIL"))
    idxCopia = ObterIndiceColunaPorSinonimos(tblE, Array("CC", "COPIA", "COM COPIA"))
    idxCco = ObterIndiceColunaPorSinonimos(tblE, Array("CCO", "BCC", "COPIA OCULTA"))

    If idxPara = 0 And tblE.ListColumns.Count >= 1 Then idxPara = 1
    If idxCopia = 0 And tblE.ListColumns.Count >= 2 Then idxCopia = 2
    If idxCco = 0 And tblE.ListColumns.Count >= 3 Then idxCco = 3

    If idxPara > 0 Then sPara = ColetarEmailsColuna(tblE, idxPara)
    If idxCopia > 0 Then sCopia = ColetarEmailsColuna(tblE, idxCopia)
    If idxCco > 0 Then sCco = ColetarEmailsColuna(tblE, idxCco)

    Exit Sub

TratarErro:
    RegistrarLog "ERRO ao obter destinatarios: " & Err.Description & " (" & CStr(Err.Number) & ")"
End Sub

Private Function ObterIndiceColunaPorSinonimos(ByVal lo As ListObject, ByVal sinonimos As Variant) As Long
    Dim i As Long
    Dim j As Long
    Dim nomeColuna As String
    Dim nomeSinonimo As String

    For i = 1 To lo.ListColumns.Count
        nomeColuna = NormalizarTextoCabecalho(CStr(lo.ListColumns(i).Name))

        For j = LBound(sinonimos) To UBound(sinonimos)
            nomeSinonimo = NormalizarTextoCabecalho(CStr(sinonimos(j)))

            If nomeColuna = nomeSinonimo Then
                ObterIndiceColunaPorSinonimos = i
                Exit Function
            End If
        Next j
    Next i
End Function

Private Function ColetarEmailsColuna(ByVal lo As ListObject, ByVal indiceColuna As Long) As String
    Dim i As Long
    Dim valorAtual As String
    Dim resultado As String

    If indiceColuna <= 0 Then Exit Function
    If lo.DataBodyRange Is Nothing Then Exit Function

    For i = 1 To lo.ListRows.Count
        valorAtual = Trim$(CStr(lo.DataBodyRange.Cells(i, indiceColuna).Value))

        If Len(valorAtual) > 0 Then
            If Len(resultado) > 0 Then
                resultado = resultado & "; "
            End If
            resultado = resultado & valorAtual
        End If
    Next i

    ColetarEmailsColuna = resultado
End Function

Private Sub RegistrarLog(ByVal msg As String)
    Dim linha As String
    Dim prefixoId As String
    Dim fsoLog As Object
    Dim txtStream As Object

    If m_blnInLogWrite Then Exit Sub
    m_blnInLogWrite = True

    If Len(m_execId) > 0 Then
        prefixoId = "[ExecId:" & m_execId & "] "
    Else
        prefixoId = vbNullString
    End If

    On Error Resume Next

    GarantirPastaDoLog ObterCaminhoLog()

    Set fsoLog = CreateObject("Scripting.FileSystemObject")
    linha = "[" & Format$(Now, "dd/MM/yyyy HH:mm:ss") & "] [VBA] [INFO] " & prefixoId & SanitizarTextoLog(msg)
    Set txtStream = fsoLog.OpenTextFile(ObterCaminhoLog(), 8, True)
    If Err.Number = 0 Then
        txtStream.WriteLine linha
        txtStream.Close
    End If
    Set txtStream = Nothing
    Set fsoLog = Nothing

    On Error GoTo 0
    m_blnInLogWrite = False
End Sub

Private Function SanitizarTextoLog(ByVal texto As String) As String
    texto = Replace(texto, vbCr, " ")
    texto = Replace(texto, vbLf, " ")
    texto = Replace(texto, vbTab, " ")
    texto = RemoverAcentos(texto)
    texto = SomenteAsciiSeguro(texto)

    Do While InStr(1, texto, "  ", vbBinaryCompare) > 0
        texto = Replace(texto, "  ", " ")
    Loop

    SanitizarTextoLog = Trim$(texto)
End Function

Private Function NormalizeExecId(ByVal texto As String) As String
    Dim i As Long
    Dim codigo As Long
    Dim ch As String
    Dim resultado As String

    texto = Trim$(texto)
    If Len(texto) = 0 Then
        NormalizeExecId = vbNullString
        Exit Function
    End If

    texto = RemoverAcentos(texto)

    For i = 1 To Len(texto)
        ch = Mid$(texto, i, 1)
        codigo = AscW(ch)

        If codigo < 0 Then codigo = codigo + 65536

        If (codigo >= 48 And codigo <= 57) _
           Or (codigo >= 65 And codigo <= 90) _
           Or (codigo >= 97 And codigo <= 122) _
           Or ch = "_" _
           Or ch = "-" Then
            resultado = resultado & ch
        Else
            resultado = resultado & "_"
        End If
    Next i

    If Len(resultado) > 64 Then resultado = Left$(resultado, 64)
    NormalizeExecId = resultado
End Function

Private Function RemoverAcentos(ByVal texto As String) As String
    texto = Replace(texto, ChrW$(193), "A")
    texto = Replace(texto, ChrW$(192), "A")
    texto = Replace(texto, ChrW$(194), "A")
    texto = Replace(texto, ChrW$(195), "A")
    texto = Replace(texto, ChrW$(196), "A")
    texto = Replace(texto, ChrW$(225), "a")
    texto = Replace(texto, ChrW$(224), "a")
    texto = Replace(texto, ChrW$(226), "a")
    texto = Replace(texto, ChrW$(227), "a")
    texto = Replace(texto, ChrW$(228), "a")

    texto = Replace(texto, ChrW$(201), "E")
    texto = Replace(texto, ChrW$(200), "E")
    texto = Replace(texto, ChrW$(202), "E")
    texto = Replace(texto, ChrW$(203), "E")
    texto = Replace(texto, ChrW$(233), "e")
    texto = Replace(texto, ChrW$(232), "e")
    texto = Replace(texto, ChrW$(234), "e")
    texto = Replace(texto, ChrW$(235), "e")

    texto = Replace(texto, ChrW$(205), "I")
    texto = Replace(texto, ChrW$(204), "I")
    texto = Replace(texto, ChrW$(206), "I")
    texto = Replace(texto, ChrW$(207), "I")
    texto = Replace(texto, ChrW$(237), "i")
    texto = Replace(texto, ChrW$(236), "i")
    texto = Replace(texto, ChrW$(238), "i")
    texto = Replace(texto, ChrW$(239), "i")

    texto = Replace(texto, ChrW$(211), "O")
    texto = Replace(texto, ChrW$(210), "O")
    texto = Replace(texto, ChrW$(212), "O")
    texto = Replace(texto, ChrW$(213), "O")
    texto = Replace(texto, ChrW$(214), "O")
    texto = Replace(texto, ChrW$(243), "o")
    texto = Replace(texto, ChrW$(242), "o")
    texto = Replace(texto, ChrW$(244), "o")
    texto = Replace(texto, ChrW$(245), "o")
    texto = Replace(texto, ChrW$(246), "o")

    texto = Replace(texto, ChrW$(218), "U")
    texto = Replace(texto, ChrW$(217), "U")
    texto = Replace(texto, ChrW$(219), "U")
    texto = Replace(texto, ChrW$(220), "U")
    texto = Replace(texto, ChrW$(250), "u")
    texto = Replace(texto, ChrW$(249), "u")
    texto = Replace(texto, ChrW$(251), "u")
    texto = Replace(texto, ChrW$(252), "u")

    texto = Replace(texto, ChrW$(199), "C")
    texto = Replace(texto, ChrW$(231), "c")
    texto = Replace(texto, ChrW$(209), "N")
    texto = Replace(texto, ChrW$(241), "n")

    texto = Replace(texto, ChrW$(8211), "-")
    texto = Replace(texto, ChrW$(8212), "-")
    texto = Replace(texto, ChrW$(8220), """")
    texto = Replace(texto, ChrW$(8221), """")
    texto = Replace(texto, ChrW$(8216), "'")
    texto = Replace(texto, ChrW$(8217), "'")

    RemoverAcentos = texto
End Function

Private Function SomenteAsciiSeguro(ByVal texto As String) As String
    Dim i As Long
    Dim codigo As Long
    Dim ch As String
    Dim resultado As String

    For i = 1 To Len(texto)
        ch = Mid$(texto, i, 1)
        codigo = AscW(ch)

        If codigo < 0 Then codigo = codigo + 65536

        If codigo >= 32 And codigo <= 126 Then
            resultado = resultado & ch
        Else
            resultado = resultado & " "
        End If
    Next i

    SomenteAsciiSeguro = resultado
End Function

Private Function LerArquivoUtf8(ByVal caminho As String) As String
    Dim stm As Object

    On Error GoTo Falha

    If Dir$(caminho) = vbNullString Then
        LerArquivoUtf8 = vbNullString
        Exit Function
    End If

    Set stm = CreateObject("ADODB.Stream")
    stm.Type = 2
    stm.Charset = "utf-8"
    stm.Open
    stm.LoadFromFile caminho

    LerArquivoUtf8 = stm.ReadText(-1)

    stm.Close
    Set stm = Nothing
    Exit Function

Falha:
    On Error Resume Next
    If Not stm Is Nothing Then
        stm.Close
        Set stm = Nothing
    End If
    LerArquivoUtf8 = vbNullString
End Function

Private Sub GravarArquivoUtf8(ByVal caminho As String, ByVal conteudo As String)
    Dim stm As Object

    On Error GoTo Falha

    Set stm = CreateObject("ADODB.Stream")
    stm.Type = 2
    stm.Charset = "utf-8"
    stm.Open
    stm.WriteText conteudo
    stm.SaveToFile caminho, 2

    stm.Close
    Set stm = Nothing
    Exit Sub

Falha:
    On Error Resume Next
    If Not stm Is Nothing Then
        stm.Close
        Set stm = Nothing
    End If
End Sub

Private Sub GarantirPastaDoLog(ByVal caminhoArquivo As String)
    Dim pastaLog As String
    Dim fso As Object
    Dim partes() As String
    Dim i As Long
    Dim caminhoAtual As String

    pastaLog = ObterPastaDoArquivo(caminhoArquivo)
    If Len(pastaLog) = 0 Then Exit Sub

    Set fso = CreateObject("Scripting.FileSystemObject")

    If fso.FolderExists(pastaLog) Then Exit Sub

    partes = Split(pastaLog, "\")

    If UBound(partes) < 1 Then Exit Sub

    caminhoAtual = partes(0) & "\"

    For i = 1 To UBound(partes)
        If Len(partes(i)) > 0 Then
            caminhoAtual = caminhoAtual & partes(i)

            If Not fso.FolderExists(caminhoAtual) Then
                fso.CreateFolder caminhoAtual
            End If

            caminhoAtual = caminhoAtual & "\"
        End If
    Next i
End Sub

Private Function ObterPastaDoArquivo(ByVal caminhoCompleto As String) As String
    Dim pos As Long

    pos = InStrRev(caminhoCompleto, "\")

    If pos > 0 Then
        ObterPastaDoArquivo = Left$(caminhoCompleto, pos - 1)
    Else
        ObterPastaDoArquivo = vbNullString
    End If
End Function

Private Function ObterTabela(ByVal ws As Worksheet, ByVal nomeTabela As String) As ListObject
    On Error Resume Next
    Set ObterTabela = ws.ListObjects(nomeTabela)
    On Error GoTo 0
End Function

Private Function ObterListColumn(ByVal lo As ListObject, ByVal nomeColuna As String) As ListColumn
    Dim lc As ListColumn

    For Each lc In lo.ListColumns
        If StrComp(Trim$(CStr(lc.Name)), Trim$(nomeColuna), vbTextCompare) = 0 Then
            Set ObterListColumn = lc
            Exit Function
        End If
    Next lc
End Function

Private Function NormalizarTextoCabecalho(ByVal texto As String) As String
    texto = UCase$(Trim$(texto))
    texto = RemoverAcentos(texto)
    texto = Replace(texto, "_", " ")
    texto = Replace(texto, "-", " ")
    texto = Replace(texto, ".", " ")

    Do While InStr(1, texto, "  ", vbBinaryCompare) > 0
        texto = Replace(texto, "  ", " ")
    Loop

    NormalizarTextoCabecalho = Trim$(texto)
End Function

Private Function NomeColunaDataUltimaProd() As String
    NomeColunaDataUltimaProd = "Data " & ChrW$(218) & "ltima Prod."
End Function

Private Function NomeColunaDataBloqueio() As String
    NomeColunaDataBloqueio = "Data Bloqueio"
End Function

Private Function NomeColunaPrevisaoLiberar() As String
    NomeColunaPrevisaoLiberar = "Previs" & ChrW$(227) & "o de Liberar"
End Function

Private Function TextoEmailAssuntoPrefixo() As String
    TextoEmailAssuntoPrefixo = "Alerta: Receitas Bloqueadas - "
End Function

Private Function TextoEmailTitulo() As String
    TextoEmailTitulo = "Relat" & ChrW$(243) & "rio de Receitas Bloqueadas"
End Function

Private Function TextoEmailIntro() As String
    TextoEmailIntro = "Atualizado em "
End Function

Private Function TextoEmailRodape() As String
    TextoEmailRodape = "Por favor, atualizar os status com as previs" & ChrW$(245) & "es de liberar cada receita."
End Function

Private Function TextoEmailAssinatura() As String
    TextoEmailAssinatura = "Mensagem autom" & ChrW$(225) & "tica gerada pelo VBA."
End Function

' ====================================================================================
' SMOKE TEST - Executar via VBE sem disparar conexoes ou envio de e-mail
' ====================================================================================
Public Sub TestarLogger()
    Dim idEntrada As String
    Dim idSaida   As String

    idEntrada = "Teste ExecId #01 com espaco & acento!"
    idSaida = NormalizeExecId(idEntrada)

    Debug.Print "=== TestarLogger: modReceitasBloqueadas ==="
    Debug.Print "Input  : [" & idEntrada & "]"
    Debug.Print "ExecId : [" & idSaida & "]"
    Debug.Print "Log    : " & ObterCaminhoLog()

    m_execId = idSaida

    RegistrarLog "SMOKE 1: mensagem simples sem acento"
    RegistrarLog "SMOKE 2: acento: execucao, acao, configuracao"
    RegistrarLog "SMOKE 3: chars especiais: & < > ; -- SELECT 1"
    RegistrarLog "SMOKE 4: tab" & vbTab & " e newline" & vbCrLf & "inline"

    m_execId = vbNullString

    Debug.Print "Concluido. Verifique: " & ObterCaminhoLog()
End Sub


