Attribute VB_Name = "ModuloPrincipal"
Option Explicit

Private gLogFile As String
Private gLogReady As Boolean
Private gInLogWrite As Boolean
Private Const LOG_MAX_LINES As Long = 5000
Private Const LOG_FOLDER As String = "C:\Automacoes\Receitas Emitidas\Logs"
Private Const DEFAULT_RECIPIENT_TO As String = "acacio.klann@costaricamalhas.ind.br"
Private Const CONFIG_SHEET_NAME As String = "Config"
Private Const CONFIG_TABLE_NAME As String = "EnderecosEmail"
Private Const ITEM_SEPARATOR_CODE As Long = 30
Private Const FIELD_SEPARATOR_CODE As Long = 31

Private mExecId As String

Private Type ReportStats
    MachineCount As Long
    RecipeCount As Long
    TotalWeight As Long
    MaxMachineWeight As Long
End Type

Private Type LayoutProfile
    ContainerWidth As Long
    ColumnCount As Long
    ColumnGap As Long
    ColumnWidth As Long
    ObWidth As Long
    InicioWidth As Long
    OuterPad As Long
    TitleFontPt As Double
    MetaFontPt As Double
    SectionFontPt As Double
    HeaderFontPt As Double
    BodyFontPt As Double
    TitleLinePx As Long
    MetaLinePx As Long
    SectionLinePx As Long
    HeaderLinePx As Long
    BodyLinePx As Long
    RowPadY As Long
    RowPadX As Long
    BlockPadY As Long
    SpacerHeight As Long
End Type

Public Sub AtualizarEEnviarOutlook(Optional ByVal execId As String = "", Optional ByVal previewOnly As Boolean = False)
    On Error GoTo TratarErro

    Dim pivotTable As pivotTable
    Dim sourceRange As Range

    mExecId = NormalizeExecId(execId)
    InitLog

    WriteLog "INFO", "MACRO", "Rotina iniciada"

    Set pivotTable = ObterPivotControleReceitas()
    If pivotTable Is Nothing Then
        Err.Raise vbObjectError + 5002, , "Nenhuma Tabela Dinamica foi encontrada na pasta de trabalho"
    End If

    WriteLog "INFO", "PIVOT", "Tabela Dinamica localizada: " & pivotTable.Name & " | Aba: " & pivotTable.Parent.Name

    AtualizarConsultaControleReceitas

    WriteLog "INFO", "PIVOT", "Iniciando atualizacao da Tabela Dinamica"
    pivotTable.RefreshTable
    WriteLog "INFO", "PIVOT", "Tabela Dinamica atualizada com sucesso"

    Set sourceRange = pivotTable.TableRange1
    If sourceRange Is Nothing Then
        Err.Raise vbObjectError + 5003, , "Nao foi possivel obter o intervalo da Tabela Dinamica"
    End If

    WriteLog "INFO", "PIVOT", "Intervalo capturado: " & sourceRange.Address(False, False)

    EnviarEmailOutlookAdaptativo sourceRange, previewOnly

    WriteLog "INFO", "MACRO", "Rotina finalizada com sucesso"
    FinalizeLog True
    Exit Sub

TratarErro:
    Dim errNum As Long, errSrc As String, errDesc As String
    errNum = Err.Number: errSrc = Err.Source: errDesc = Err.Description
    If gLogReady Then
        WriteLog "ERROR", "MACRO", "Erro " & errNum & " - " & errDesc
        FinalizeLog False
    End If
    If errNum <> 0 Then Err.Raise errNum, errSrc, errDesc
End Sub

Public Sub PreVisualizarOutlook()
    AtualizarEEnviarOutlook vbNullString, True
End Sub

Public Sub EnviarOutlook()
    AtualizarEEnviarOutlook vbNullString, False
End Sub

Private Sub EnviarEmailOutlookAdaptativo(ByVal sourceRange As Range, Optional ByVal previewOnly As Boolean = False)
    On Error GoTo TratarErro

    Dim outlookApp As Object
    Dim outlookMail As Object
    Dim outlookInspector As Object
    Dim htmlBody As String
    Dim signatureHtml As String
    Dim recipientTo As String
        Dim sendErr As Long, sendDesc As String
    Set outlookApp = PrepararOutlook()

    If outlookApp Is Nothing Then
        Err.Raise vbObjectError + 5004, , "Outlook inacessivel apos tentativas de inicializacao"
    End If

    Set outlookMail = outlookApp.CreateItem(0)

    If outlookMail Is Nothing Then
        Err.Raise vbObjectError + 5005, , "Nao foi possivel criar MailItem"
    End If

    WriteLog "INFO", "EMAIL", "MailItem criado com sucesso"

    htmlBody = MontarHtmlAdaptativo(sourceRange)

    recipientTo = GetRecipientTo()
    WriteLog "INFO", "EMAIL", "TO=" & recipientTo
    If Len(recipientTo) = 0 Or InStr(1, recipientTo, "@") = 0 Then
        Err.Raise vbObjectError + 5006, , "Destinatario de email nao informado ou invalido"
    End If

    With outlookMail
            WriteLog "INFO", "EMAIL", "Definindo Subject"
            .Subject = GetEmailSubject()
            WriteLog "INFO", "EMAIL", "Definindo To"
            .To = recipientTo
            WriteLog "INFO", "EMAIL", "Adicionando anexo"
            .Attachments.Add ThisWorkbook.FullName
            WriteLog "INFO", "EMAIL", "Anexo adicionado: " & ThisWorkbook.Name
            WriteLog "INFO", "EMAIL", "Definindo HTMLBody"
            .htmlBody = htmlBody
            WriteLog "INFO", "EMAIL", "HTMLBody montado com sucesso"

        If previewOnly Then
                WriteLog "INFO", "EMAIL", "Chamando Display"
                .Display
                WriteLog "INFO", "EMAIL", "Email exibido em modo de pre-visualizacao"
        Else
                WriteLog "INFO", "EMAIL", "Chamando Send"
                On Error Resume Next
                .Send
                sendErr = Err.Number: sendDesc = Err.Description
                On Error GoTo TratarErro
                If sendErr <> 0 Then
                    WriteLog "ERROR", "EMAIL", "Send falhou | Err=" & sendErr & " | Desc=" & sendDesc
                    Err.Raise sendErr, "EMAIL.Send", sendDesc
                End If
                WriteLog "INFO", "EMAIL", "E-mail enviado com sucesso"
        End If
    End With

    Set outlookMail = Nothing
    Set outlookApp = Nothing
    Exit Sub

TratarErro:
    Dim errNum As Long, errSrc As String, errDesc As String
    errNum = Err.Number: errSrc = Err.Source: errDesc = Err.Description
    WriteLog "ERROR", "EMAIL", "Erro " & errNum & " - " & errDesc
    On Error Resume Next
    Set outlookMail = Nothing
    Set outlookApp = Nothing
    On Error GoTo 0
    If errNum <> 0 Then Err.Raise errNum, errSrc, errDesc
End Sub

Private Function PrepararOutlook() As Object
    Dim oApp As Object

    On Error Resume Next

    Set oApp = GetObject(, "Outlook.Application")
    If Not oApp Is Nothing Then
        WriteLog "INFO", "EMAIL", "Outlook conectado por instancia existente"
        Set PrepararOutlook = oApp
        Exit Function
    End If

    Err.Clear
    Set oApp = CreateObject("Outlook.Application")
    If Not oApp Is Nothing Then
        WriteLog "INFO", "EMAIL", "Outlook iniciado por nova instancia"
        Set PrepararOutlook = oApp
        Exit Function
    End If

    WriteLog "WARN", "EMAIL", "Outlook nao respondeu. Tentando iniciar via Shell"

    Err.Clear
    Shell "outlook.exe", 2
    Application.Wait Now + TimeValue("0:00:08")
    Set oApp = GetObject(, "Outlook.Application")
    If Not oApp Is Nothing Then
        WriteLog "INFO", "EMAIL", "Outlook iniciado via Shell"
        Set PrepararOutlook = oApp
        Exit Function
    End If

    WriteLog "ERROR", "EMAIL", "FALHA FINAL: Nao foi possivel iniciar o Outlook"
    On Error GoTo 0
End Function

Private Function MontarHtmlAdaptativo(ByVal sourceRange As Range) As String
    On Error GoTo TratarErro

    Dim machineOrder As Collection
    Dim dictMachineGroups As Object
    Dim dictGroupDetails As Object
    Dim dictMachineWeight As Object
    Dim dictMachineRecipeCount As Object

    Dim stats As ReportStats
    Dim profile As LayoutProfile

    Dim columnHtml() As String
    Dim columnWeight() As Long
    Dim machineItem As Variant
    Dim columnIndex As Long

    Set machineOrder = New Collection
    Set dictMachineGroups = CreateObject("Scripting.Dictionary")
    Set dictGroupDetails = CreateObject("Scripting.Dictionary")
    Set dictMachineWeight = CreateObject("Scripting.Dictionary")
    Set dictMachineRecipeCount = CreateObject("Scripting.Dictionary")

    ParsePivotRange sourceRange, _
                    machineOrder, _
                    dictMachineGroups, _
                    dictGroupDetails, _
                    dictMachineWeight, _
                    dictMachineRecipeCount, _
                    stats

    If machineOrder.Count = 0 Then
        Err.Raise vbObjectError + 5010, , "Nenhum dado valido foi encontrado para montar o email"
    End If

    BuildLayoutProfile stats, profile

    WriteLog "INFO", "HTML", _
        "Perfil calculado | Colunas=" & profile.ColumnCount & _
        " | Width=" & profile.ContainerWidth & _
        " | BodyFontPt=" & FormatNumberInvariant(profile.BodyFontPt, "0.0") & _
        " | TotalWeight=" & stats.TotalWeight & _
        " | Maquinas=" & stats.MachineCount & _
        " | Receitas=" & stats.RecipeCount

    ReDim columnHtml(1 To profile.ColumnCount)
    ReDim columnWeight(1 To profile.ColumnCount)

    For Each machineItem In machineOrder
        columnIndex = GetLightestColumnIndex(columnWeight)
        columnHtml(columnIndex) = columnHtml(columnIndex) & _
                                  BuildMachineBlock(CStr(machineItem), _
                                                    dictMachineGroups, _
                                                    dictGroupDetails, _
                                                    dictMachineRecipeCount, _
                                                    profile)
        columnWeight(columnIndex) = columnWeight(columnIndex) + CLng(dictMachineWeight(CStr(machineItem)))
    Next machineItem

    MontarHtmlAdaptativo = BuildDocumentHtml(columnHtml, stats, profile)
    Exit Function

TratarErro:
    Dim errNum As Long, errSrc As String, errDesc As String
    errNum = Err.Number: errSrc = Err.Source: errDesc = Err.Description
    WriteLog "ERROR", "HTML", "Erro " & errNum & " - " & errDesc
    If errNum <> 0 Then Err.Raise errNum, errSrc, errDesc
End Function

Private Sub ParsePivotRange( _
    ByVal sourceRange As Range, _
    ByRef machineOrder As Collection, _
    ByRef dictMachineGroups As Object, _
    ByRef dictGroupDetails As Object, _
    ByRef dictMachineWeight As Object, _
    ByRef dictMachineRecipeCount As Object, _
    ByRef stats As ReportStats)

    On Error GoTo TratarErro

    Dim dataMatrix As Variant
    Dim rowIndex As Long
    Dim rowCount As Long
    Dim valueA As String
    Dim valueB As String
    Dim currentMachine As String
    Dim currentGroup As String

    If sourceRange Is Nothing Then
        Err.Raise vbObjectError + 5011, , "Intervalo de origem nao informado"
    End If

    If sourceRange.Columns.Count < 2 Then
        Err.Raise vbObjectError + 5012, , "A Tabela Dinamica precisa ter pelo menos 2 colunas"
    End If

    dataMatrix = sourceRange.Resize(sourceRange.Rows.Count, 2).Value2
    rowCount = sourceRange.Rows.Count

    currentMachine = vbNullString
    currentGroup = "0"

    For rowIndex = 1 To rowCount
        valueA = GetMatrixText(dataMatrix, rowIndex, 1, False)
        valueB = GetMatrixText(dataMatrix, rowIndex, 2, True)

        If Not IsCabecalhoPivot(valueA, valueB) Then
            If IsLinhaMaquina(valueA) Then
                currentMachine = valueA
                currentGroup = "0"
                RegisterMachine currentMachine, machineOrder, dictMachineGroups, dictMachineWeight, dictMachineRecipeCount

            ElseIf Len(currentMachine) > 0 And IsGrupoLinha(valueA, valueB) Then
                currentGroup = valueA
                RegisterGroup currentMachine, currentGroup, machineOrder, dictMachineGroups, dictGroupDetails, dictMachineWeight, dictMachineRecipeCount

            ElseIf Len(currentMachine) > 0 And IsReceitaValida(valueA) And Len(valueB) > 0 Then
                AddDetail currentMachine, currentGroup, valueA, valueB, machineOrder, dictMachineGroups, dictGroupDetails, dictMachineWeight, dictMachineRecipeCount
            End If
        End If
    Next rowIndex

    ComputeReportStats machineOrder, dictMachineWeight, dictMachineRecipeCount, stats
    Exit Sub

TratarErro:
    Dim errNum As Long, errSrc As String, errDesc As String
    errNum = Err.Number: errSrc = Err.Source: errDesc = Err.Description
    If errNum <> 0 Then Err.Raise errNum, errSrc, errDesc
End Sub

Private Sub ComputeReportStats( _
    ByRef machineOrder As Collection, _
    ByRef dictMachineWeight As Object, _
    ByRef dictMachineRecipeCount As Object, _
    ByRef stats As ReportStats)

    Dim machineItem As Variant
    Dim machineWeight As Long
    Dim RecipeCount As Long

    stats.MachineCount = 0
    stats.RecipeCount = 0
    stats.TotalWeight = 0
    stats.MaxMachineWeight = 0

    For Each machineItem In machineOrder
        machineWeight = CLng(dictMachineWeight(CStr(machineItem)))
        RecipeCount = CLng(dictMachineRecipeCount(CStr(machineItem)))

        stats.MachineCount = stats.MachineCount + 1
        stats.RecipeCount = stats.RecipeCount + RecipeCount
        stats.TotalWeight = stats.TotalWeight + machineWeight

        If machineWeight > stats.MaxMachineWeight Then
            stats.MaxMachineWeight = machineWeight
        End If
    Next machineItem
End Sub

Private Sub BuildLayoutProfile(ByRef stats As ReportStats, ByRef profile As LayoutProfile)
    Dim volumeScore As Double
    Dim compressFactor As Double
    Dim usableWidth As Long

    volumeScore = stats.TotalWeight + (stats.MachineCount * 2.2) + stats.MaxMachineWeight + (stats.RecipeCount / 3)

    If volumeScore <= 54 Then
        compressFactor = 0
    Else
        compressFactor = (volumeScore - 54) / 72
    End If

    If compressFactor > 1 Then
        compressFactor = 1
    End If

    If volumeScore >= 72 Or stats.MaxMachineWeight >= 16 Or stats.MachineCount >= 11 Then
        profile.ColumnCount = 3
    Else
        profile.ColumnCount = 2
    End If

    profile.ContainerWidth = IIf(profile.ColumnCount = 3, 696, 680)
    profile.ColumnGap = MaxLong(6, 14 - CLng(compressFactor * 8))
    profile.OuterPad = MaxLong(4, 12 - CLng(compressFactor * 6))

    profile.TitleFontPt = ClampDouble(13.5 - (compressFactor * 2.7), 10.5, 13.5)
    profile.MetaFontPt = ClampDouble(8.4 - (compressFactor * 1.8), 6.3, 8.4)
    profile.SectionFontPt = ClampDouble(8.4 - (compressFactor * 2#), 6.1, 8.4)
    profile.HeaderFontPt = ClampDouble(7.9 - (compressFactor * 1.8), 5.9, 7.9)
    profile.BodyFontPt = ClampDouble(7.8 - (compressFactor * 2.2), 5.6, 7.8)

    profile.RowPadY = MaxLong(1, 4 - CLng(compressFactor * 3))
    profile.RowPadX = MaxLong(3, 6 - CLng(compressFactor * 3))
    profile.BlockPadY = MaxLong(3, 6 - CLng(compressFactor * 3))
    profile.SpacerHeight = MaxLong(2, 6 - CLng(compressFactor * 4))

    profile.TitleLinePx = MaxLong(13, CLng(profile.TitleFontPt * 1.35))
    profile.MetaLinePx = MaxLong(9, CLng(profile.MetaFontPt * 1.35))
    profile.SectionLinePx = MaxLong(9, CLng(profile.SectionFontPt * 1.35))
    profile.HeaderLinePx = MaxLong(8, CLng(profile.HeaderFontPt * 1.35))
    profile.BodyLinePx = MaxLong(8, CLng(profile.BodyFontPt * 1.35))

    usableWidth = profile.ContainerWidth - ((profile.ColumnCount - 1) * profile.ColumnGap)
    profile.ColumnWidth = usableWidth \ profile.ColumnCount
    profile.ObWidth = CLng(profile.ColumnWidth * 0.47)
    profile.InicioWidth = profile.ColumnWidth - profile.ObWidth
End Sub

Private Function BuildDocumentHtml( _
    ByRef columnHtml() As String, _
    ByRef stats As ReportStats, _
    ByRef profile As LayoutProfile) As String

    Dim html As String
    Dim headerRowHtml As String
    Dim contentRowHtml As String
    Dim index As Long

    headerRowHtml = vbNullString
    contentRowHtml = vbNullString

    For index = LBound(columnHtml) To UBound(columnHtml)
        If Len(columnHtml(index)) = 0 Then
            columnHtml(index) = BuildEmptyColumn(profile)
        End If

        headerRowHtml = headerRowHtml & _
            "<td width='" & profile.ColumnWidth & "' align='center' valign='middle' " & _
            "style='width:" & profile.ColumnWidth & "px;padding:" & profile.BlockPadY & "px " & profile.RowPadX & "px;" & _
            "border:1px solid #000000;background-color:#D9E2F3;font-family:Arial,Calibri,sans-serif;" & _
            "font-size:" & FormatPt(profile.HeaderFontPt) & ";font-weight:bold;line-height:" & profile.HeaderLinePx & "px;" & _
            "text-align:center;'>M&aacute;quina / Grupo / OB / In&iacute;cio</td>"

        contentRowHtml = contentRowHtml & _
            "<td width='" & profile.ColumnWidth & "' valign='top' " & _
            "style='width:" & profile.ColumnWidth & "px;padding-top:" & profile.BlockPadY & "px;vertical-align:top;'>" & _
            columnHtml(index) & "</td>"

        If index < UBound(columnHtml) Then
            headerRowHtml = headerRowHtml & _
                "<td width='" & profile.ColumnGap & "' style='width:" & profile.ColumnGap & "px;font-size:0;line-height:0;'>&nbsp;</td>"

            contentRowHtml = contentRowHtml & _
                "<td width='" & profile.ColumnGap & "' style='width:" & profile.ColumnGap & "px;font-size:0;line-height:0;'>&nbsp;</td>"
        End If
    Next index

    html = vbNullString
    html = html & "<html><head>"
    html = html & "<meta http-equiv='Content-Type' content='text/html; charset=utf-8'>"
    html = html & "<meta name='x-apple-disable-message-reformatting'>"
    html = html & "<style>"
    html = html & "@page WordSection1 { size:595.3pt 841.9pt; margin:14pt 14pt 14pt 14pt; }"
    html = html & "div.WordSection1 { page:WordSection1; }"
    html = html & "table { border-collapse:collapse; mso-table-lspace:0pt; mso-table-rspace:0pt; }"
    html = html & "td { mso-line-height-rule:exactly; }"
    html = html & "</style>"
    html = html & "</head>"

    html = html & "<body style='margin:0;padding:0;background-color:#FFFFFF;'>"
    html = html & "<div class='WordSection1'>"
    html = html & "<table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='width:100%;background-color:#FFFFFF;'>"
    html = html & "<tr><td align='center' style='padding:" & profile.OuterPad & "px;'>"

    html = html & "<!--[if mso]><table role='presentation' border='0' cellspacing='0' cellpadding='0' width='" & profile.ContainerWidth & "'><tr><td><![endif]-->"
    html = html & "<table role='presentation' border='0' cellspacing='0' cellpadding='0' width='" & profile.ContainerWidth & "' style='width:" & profile.ContainerWidth & "px;background-color:#FFFFFF;'>"

    html = html & "<tr>"
    html = html & "<td style='padding:" & profile.BlockPadY & "px " & profile.RowPadX & "px;border:1px solid #D9E2F3;background-color:#FFFFFF;'>"

    html = html & "<table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='width:100%;'>"
    html = html & "<tr><td align='center' style='padding:0 0 2px 0;font-family:Arial,Calibri,sans-serif;font-size:" & FormatPt(profile.TitleFontPt) & ";font-weight:bold;line-height:" & profile.TitleLinePx & "px;color:#000000;text-align:center;'>Controle de Receitas Emitidas</td></tr>"
    html = html & "<tr><td align='center' style='padding:0 0 2px 0;font-family:Arial,Calibri,sans-serif;font-size:" & FormatPt(profile.MetaFontPt) & ";line-height:" & profile.MetaLinePx & "px;color:#333333;text-align:center;'>Confer&ecirc;ncia f&iacute;sica - cozinha de qu&iacute;micos</td></tr>"
    html = html & "<tr><td align='center' style='padding:0 0 " & profile.BlockPadY & "px 0;font-family:Arial,Calibri,sans-serif;font-size:" & FormatPt(profile.MetaFontPt) & ";line-height:" & profile.MetaLinePx & "px;color:#333333;text-align:center;'>Emitido em " & Format(Now, "dd/mm/yyyy HH:nn") & " | M&aacute;quinas listadas: " & stats.MachineCount & " | Receitas: " & stats.RecipeCount & "</td></tr>"
    html = html & "</table>"

    html = html & "<table role='presentation' border='0' cellspacing='0' cellpadding='0' width='100%' style='width:100%;'>"
    html = html & "<tr>" & headerRowHtml & "</tr>"
    html = html & "<tr>" & contentRowHtml & "</tr>"
    html = html & "</table>"

    html = html & "</td>"
    html = html & "</tr>"

    html = html & "</table>"
    html = html & "<!--[if mso]></td></tr></table><![endif]-->"

    html = html & "</td></tr>"
    html = html & "</table>"
    html = html & "</div>"
    html = html & "</body></html>"

    BuildDocumentHtml = html
End Function

Private Function BuildMachineBlock( _
    ByVal machineName As String, _
    ByRef dictMachineGroups As Object, _
    ByRef dictGroupDetails As Object, _
    ByRef dictMachineRecipeCount As Object, _
    ByRef profile As LayoutProfile) As String

    Dim html As String
    Dim groupList As String
    Dim groupsArray() As String
    Dim groupIndex As Long
    Dim groupName As String
    Dim groupKey As String
    Dim RecipeCount As Long

    RecipeCount = CLng(dictMachineRecipeCount(machineName))
    groupList = CStr(dictMachineGroups(machineName))
    groupsArray = Split(groupList, "|")

    html = vbNullString
    html = html & "<table role='presentation' border='0' cellspacing='0' cellpadding='0' width='" & profile.ColumnWidth & "' style='width:" & profile.ColumnWidth & "px;margin:0;page-break-inside:avoid;'>"

    html = html & "<tr>"
    html = html & "<td colspan='2' align='center' style='padding:" & profile.BlockPadY & "px " & profile.RowPadX & "px;border:1px solid #000000;background-color:#E9EEF7;font-family:Arial,Calibri,sans-serif;font-size:" & FormatPt(profile.SectionFontPt) & ";font-weight:bold;line-height:" & profile.SectionLinePx & "px;text-align:center;'>"
    html = html & HtmlEncode(machineName) & " | " & RecipeCount & " receita"
    If RecipeCount <> 1 Then html = html & "s"
    html = html & "</td>"
    html = html & "</tr>"

    For groupIndex = LBound(groupsArray) To UBound(groupsArray)
        groupName = Trim$(groupsArray(groupIndex))

        If Len(groupName) > 0 Then
            groupKey = machineName & "||" & groupName

            If groupName <> "0" Then
                html = html & "<tr>"
                html = html & "<td colspan='2' align='center' style='padding:" & profile.RowPadY & "px " & profile.RowPadX & "px;border-left:1px solid #000000;border-right:1px solid #000000;border-bottom:1px solid #D9D9D9;background-color:#F2F2F2;font-family:Arial,Calibri,sans-serif;font-size:" & FormatPt(profile.HeaderFontPt) & ";font-weight:bold;line-height:" & profile.HeaderLinePx & "px;text-align:center;'>"
                html = html & "Grupo " & HtmlEncode(groupName)
                html = html & "</td>"
                html = html & "</tr>"
            End If

            If dictGroupDetails.Exists(groupKey) Then
                html = html & BuildDetailRows(CStr(dictGroupDetails(groupKey)), profile)
            End If
        End If
    Next groupIndex

    html = html & "<tr><td colspan='2' style='height:" & profile.SpacerHeight & "px;font-size:0;line-height:0;border-left:1px solid #000000;border-right:1px solid #000000;border-bottom:1px solid #000000;'>&nbsp;</td></tr>"
    html = html & "</table>"
    html = html & "<table role='presentation' border='0' cellspacing='0' cellpadding='0' width='" & profile.ColumnWidth & "' style='width:" & profile.ColumnWidth & "px;'><tr><td height='" & profile.SpacerHeight & "' style='height:" & profile.SpacerHeight & "px;font-size:0;line-height:0;'>&nbsp;</td></tr></table>"

    BuildMachineBlock = html
End Function

Private Function BuildDetailRows(ByVal encodedRows As String, ByRef profile As LayoutProfile) As String
    Dim html As String
    Dim items() As String
    Dim fields() As String
    Dim itemIndex As Long
    Dim obText As String
    Dim inicioText As String
    Dim itemSeparator As String
    Dim fieldSeparator As String

    If Len(encodedRows) = 0 Then Exit Function

    itemSeparator = Chr$(ITEM_SEPARATOR_CODE)
    fieldSeparator = Chr$(FIELD_SEPARATOR_CODE)

    items = Split(encodedRows, itemSeparator)

    For itemIndex = LBound(items) To UBound(items)
        If Len(items(itemIndex)) > 0 Then
            fields = Split(items(itemIndex), fieldSeparator)

            obText = fields(0)
            If UBound(fields) >= 1 Then
                inicioText = fields(1)
            Else
                inicioText = vbNullString
            End If

            html = html & "<tr>"
            html = html & "<td width='" & profile.ObWidth & "' style='width:" & profile.ObWidth & "px;padding:" & profile.RowPadY & "px " & profile.RowPadX & "px;border-left:1px solid #000000;border-bottom:1px solid #D9D9D9;font-family:Arial,Calibri,sans-serif;font-size:" & FormatPt(profile.BodyFontPt) & ";line-height:" & profile.BodyLinePx & "px;color:#000000;white-space:nowrap;'>" & HtmlEncode(obText) & "</td>"
            html = html & "<td width='" & profile.InicioWidth & "' align='center' style='width:" & profile.InicioWidth & "px;padding:" & profile.RowPadY & "px " & profile.RowPadX & "px;border-right:1px solid #000000;border-bottom:1px solid #D9D9D9;font-family:Arial,Calibri,sans-serif;font-size:" & FormatPt(profile.BodyFontPt) & ";line-height:" & profile.BodyLinePx & "px;color:#000000;white-space:nowrap;text-align:center;'>" & HtmlEncode(inicioText) & "</td>"
            html = html & "</tr>"
        End If
    Next itemIndex

    BuildDetailRows = html
End Function

Private Function BuildEmptyColumn(ByRef profile As LayoutProfile) As String
    BuildEmptyColumn = "<table role='presentation' border='0' cellspacing='0' cellpadding='0' width='" & profile.ColumnWidth & "' style='width:" & profile.ColumnWidth & "px;'><tr><td style='height:1px;font-size:0;line-height:0;'>&nbsp;</td></tr></table>"
End Function

Private Function GetLightestColumnIndex(ByRef columnWeight() As Long) As Long
    Dim index As Long
    Dim bestIndex As Long
    Dim bestWeight As Long

    bestIndex = LBound(columnWeight)
    bestWeight = columnWeight(bestIndex)

    For index = LBound(columnWeight) + 1 To UBound(columnWeight)
        If columnWeight(index) < bestWeight Then
            bestWeight = columnWeight(index)
            bestIndex = index
        End If
    Next index

    GetLightestColumnIndex = bestIndex
End Function

Private Sub RegisterMachine( _
    ByVal machineName As String, _
    ByRef machineOrder As Collection, _
    ByRef dictMachineGroups As Object, _
    ByRef dictMachineWeight As Object, _
    ByRef dictMachineRecipeCount As Object)

    If Not dictMachineGroups.Exists(machineName) Then
        machineOrder.Add machineName
        dictMachineGroups.Add machineName, "|"
        dictMachineWeight.Add machineName, 1
        dictMachineRecipeCount.Add machineName, 0
    End If
End Sub

Private Sub IncrementMachineRecipeCount( _
    ByVal machineName As String, _
    ByRef dictMachineRecipeCount As Object)

    dictMachineRecipeCount(machineName) = CLng(dictMachineRecipeCount(machineName)) + 1
End Sub

Private Sub RegisterGroup( _
    ByVal machineName As String, _
    ByVal groupName As String, _
    ByRef machineOrder As Collection, _
    ByRef dictMachineGroups As Object, _
    ByRef dictGroupDetails As Object, _
    ByRef dictMachineWeight As Object, _
    ByRef dictMachineRecipeCount As Object)

    Dim groupsText As String
    Dim groupKey As String

    RegisterMachine machineName, machineOrder, dictMachineGroups, dictMachineWeight, dictMachineRecipeCount

    groupsText = CStr(dictMachineGroups(machineName))

    If InStr(1, groupsText, "|" & groupName & "|", vbTextCompare) = 0 Then
        dictMachineGroups(machineName) = groupsText & groupName & "|"

        If groupName <> "0" Then
            IncrementMachineRecipeCount machineName, dictMachineRecipeCount
            dictMachineWeight(machineName) = CLng(dictMachineWeight(machineName)) + 1
        End If
    End If

    groupKey = machineName & "||" & groupName
    If Not dictGroupDetails.Exists(groupKey) Then
        dictGroupDetails.Add groupKey, vbNullString
    End If
End Sub

Private Sub AddDetail( _
    ByVal machineName As String, _
    ByVal groupName As String, _
    ByVal obText As String, _
    ByVal inicioText As String, _
    ByRef machineOrder As Collection, _
    ByRef dictMachineGroups As Object, _
    ByRef dictGroupDetails As Object, _
    ByRef dictMachineWeight As Object, _
    ByRef dictMachineRecipeCount As Object)

    Dim groupKey As String

    RegisterGroup machineName, groupName, machineOrder, dictMachineGroups, dictGroupDetails, dictMachineWeight, dictMachineRecipeCount

    If groupName = "0" Then
        IncrementMachineRecipeCount machineName, dictMachineRecipeCount
    End If

    groupKey = machineName & "||" & groupName
    dictGroupDetails(groupKey) = AppendEncodedItem(CStr(dictGroupDetails(groupKey)), obText, inicioText)
    dictMachineWeight(machineName) = CLng(dictMachineWeight(machineName)) + 1
End Sub

Private Function AppendEncodedItem(ByVal currentValue As String, ByVal valueA As String, ByVal valueB As String) As String
    Dim itemSeparator As String
    Dim fieldSeparator As String
    Dim newItem As String

    itemSeparator = Chr$(ITEM_SEPARATOR_CODE)
    fieldSeparator = Chr$(FIELD_SEPARATOR_CODE)

    newItem = valueA & fieldSeparator & valueB

    If Len(currentValue) = 0 Then
        AppendEncodedItem = newItem
    Else
        AppendEncodedItem = currentValue & itemSeparator & newItem
    End If
End Function

Private Function GetMatrixText(ByRef dataMatrix As Variant, ByVal rowIndex As Long, ByVal colIndex As Long, ByVal treatAsDate As Boolean) As String
    Dim cellValue As Variant
    Dim numericValue As Double

    cellValue = dataMatrix(rowIndex, colIndex)

    If IsError(cellValue) Then Exit Function
    If IsEmpty(cellValue) Then Exit Function

    Select Case VarType(cellValue)
        Case vbString
            GetMatrixText = Trim$(CStr(cellValue))

        Case vbDate
            If treatAsDate Then
                GetMatrixText = Format$(CDate(cellValue), "dd/mm/yyyy hh:nn")
            Else
                GetMatrixText = Trim$(CStr(cellValue))
            End If

        Case vbDouble, vbSingle, vbCurrency, vbLong, vbInteger, vbByte
            numericValue = CDbl(cellValue)

            If treatAsDate And numericValue > 25000 And numericValue < 80000 Then
                GetMatrixText = Format$(CDate(numericValue), "dd/mm/yyyy hh:nn")
            ElseIf numericValue = Fix(numericValue) Then
                GetMatrixText = CStr(CLng(numericValue))
            Else
                GetMatrixText = FormatNumberInvariant(numericValue, "0.############")
            End If

        Case Else
            If treatAsDate And IsDate(cellValue) Then
                GetMatrixText = Format$(CDate(cellValue), "dd/mm/yyyy hh:nn")
            Else
                GetMatrixText = Trim$(CStr(cellValue))
            End If
    End Select

    GetMatrixText = Trim$(GetMatrixText)
End Function

Private Function HtmlEncode(ByVal textValue As String) As String
    textValue = Replace(textValue, "&", "&amp;")
    textValue = Replace(textValue, "<", "&lt;")
    textValue = Replace(textValue, ">", "&gt;")
    textValue = Replace(textValue, """", "&quot;")
    textValue = Replace(textValue, "'", "&#39;")
    HtmlEncode = textValue
End Function

Private Function FormatPt(ByVal valuePt As Double) As String
    FormatPt = FormatNumberInvariant(valuePt, "0.0") & "pt"
End Function

Private Function FormatNumberInvariant(ByVal numericValue As Double, ByVal mask As String) As String
    Dim textValue As String

    textValue = Format$(numericValue, mask)
    textValue = Replace(textValue, ".", "")
    textValue = Replace(textValue, ",", ".")
    FormatNumberInvariant = textValue
End Function

Private Function ClampDouble(ByVal valueToClamp As Double, ByVal minValue As Double, ByVal maxValue As Double) As Double
    If valueToClamp < minValue Then
        ClampDouble = minValue
    ElseIf valueToClamp > maxValue Then
        ClampDouble = maxValue
    Else
        ClampDouble = valueToClamp
    End If
End Function

Private Function MaxLong(ByVal valueA As Long, ByVal valueB As Long) As Long
    If valueA >= valueB Then
        MaxLong = valueA
    Else
        MaxLong = valueB
    End If
End Function

Private Function NormalizarTexto(ByVal textValue As String) As String
    Dim normalizedText As String

    normalizedText = LCase$(Trim$(textValue))

    normalizedText = Replace(normalizedText, ChrW(225), "a")
    normalizedText = Replace(normalizedText, ChrW(224), "a")
    normalizedText = Replace(normalizedText, ChrW(226), "a")
    normalizedText = Replace(normalizedText, ChrW(227), "a")
    normalizedText = Replace(normalizedText, ChrW(228), "a")

    normalizedText = Replace(normalizedText, ChrW(233), "e")
    normalizedText = Replace(normalizedText, ChrW(232), "e")
    normalizedText = Replace(normalizedText, ChrW(234), "e")
    normalizedText = Replace(normalizedText, ChrW(235), "e")

    normalizedText = Replace(normalizedText, ChrW(237), "i")
    normalizedText = Replace(normalizedText, ChrW(236), "i")
    normalizedText = Replace(normalizedText, ChrW(238), "i")
    normalizedText = Replace(normalizedText, ChrW(239), "i")

    normalizedText = Replace(normalizedText, ChrW(243), "o")
    normalizedText = Replace(normalizedText, ChrW(242), "o")
    normalizedText = Replace(normalizedText, ChrW(244), "o")
    normalizedText = Replace(normalizedText, ChrW(245), "o")
    normalizedText = Replace(normalizedText, ChrW(246), "o")

    normalizedText = Replace(normalizedText, ChrW(250), "u")
    normalizedText = Replace(normalizedText, ChrW(249), "u")
    normalizedText = Replace(normalizedText, ChrW(251), "u")
    normalizedText = Replace(normalizedText, ChrW(252), "u")

    normalizedText = Replace(normalizedText, ChrW(231), "c")

    NormalizarTexto = normalizedText
End Function

Private Function IsLinhaMaquina(ByVal textValue As String) As Boolean
    Dim normalizedText As String

    normalizedText = UCase$(Trim$(textValue))
    IsLinhaMaquina = (Left$(normalizedText, 2) = "MQ")
End Function

Private Function IsCabecalhoPivot(ByVal valueA As String, ByVal valueB As String) As Boolean
    Dim normalizedA As String
    Dim normalizedB As String

    normalizedA = NormalizarTexto(valueA)
    normalizedB = NormalizarTexto(valueB)

    If InStr(1, normalizedA, "maq", vbTextCompare) > 0 Then
        IsCabecalhoPivot = True
        Exit Function
    End If

    If InStr(1, normalizedB, "inicio", vbTextCompare) > 0 Then
        IsCabecalhoPivot = True
        Exit Function
    End If

    If normalizedA = "ob" And normalizedB = "inicio" Then
        IsCabecalhoPivot = True
    End If
End Function

Private Function IsReceitaValida(ByVal textValue As String) As Boolean
    Dim normalizedText As String

    normalizedText = Trim$(textValue)

    If Len(normalizedText) = 0 Then Exit Function
    If IsLinhaMaquina(normalizedText) Then Exit Function
    If Not IsNumeric(normalizedText) Then Exit Function
    If Len(normalizedText) < 5 Then Exit Function

    IsReceitaValida = True
End Function

Private Function IsGrupoLinha(ByVal valueA As String, ByVal valueB As String) As Boolean
    Dim normalizedText As String

    normalizedText = Trim$(valueA)

    If Len(normalizedText) = 0 Then Exit Function
    If IsLinhaMaquina(normalizedText) Then Exit Function
    If Len(Trim$(valueB)) > 0 Then Exit Function
    If Not IsNumeric(normalizedText) Then Exit Function

    IsGrupoLinha = True
End Function

Private Function ObterPivotControleReceitas() As pivotTable
    Dim worksheetItem As Worksheet
    Dim pivotTable As pivotTable

    On Error Resume Next
    Set worksheetItem = ThisWorkbook.Worksheets("ControleReceitasEmitidas")
    On Error GoTo 0

    If Not worksheetItem Is Nothing Then
        On Error Resume Next
        Set pivotTable = worksheetItem.PivotTables("AnalisePorMaquina")
        On Error GoTo 0

        If pivotTable Is Nothing Then
            If worksheetItem.PivotTables.Count > 0 Then
                Set pivotTable = worksheetItem.PivotTables(1)
            End If
        End If

        If Not pivotTable Is Nothing Then
            Set ObterPivotControleReceitas = pivotTable
            Exit Function
        End If
    End If

    For Each worksheetItem In ThisWorkbook.Worksheets
        If worksheetItem.PivotTables.Count > 0 Then
            Set ObterPivotControleReceitas = worksheetItem.PivotTables(1)
            Exit Function
        End If
    Next worksheetItem
End Function

Private Function ObterConexaoControleReceitas() As workbookConnection
    Dim workbookConnection As workbookConnection

    For Each workbookConnection In ThisWorkbook.Connections
        If StrComp(workbookConnection.Name, "ControleReceitasEmitidas", vbTextCompare) = 0 Then
            Set ObterConexaoControleReceitas = workbookConnection
            Exit Function
        End If
    Next workbookConnection

    For Each workbookConnection In ThisWorkbook.Connections
        If InStr(1, workbookConnection.Name, "ControleReceitasEmitidas", vbTextCompare) > 0 Then
            Set ObterConexaoControleReceitas = workbookConnection
            Exit Function
        End If
    Next workbookConnection
End Function

Private Sub AtualizarConsultaControleReceitas()
    On Error GoTo TratarErro

    Dim workbookConnection As workbookConnection
    Set workbookConnection = ObterConexaoControleReceitas()

    If workbookConnection Is Nothing Then
        WriteLog "ERROR", "POWER QUERY", "Conexao da consulta 'ControleReceitasEmitidas' nao encontrada"
        LogarConexoesDisponiveis
        Err.Raise vbObjectError + 5001, , "Conexao da consulta 'ControleReceitasEmitidas' nao encontrada"
    End If

    WriteLog "INFO", "POWER QUERY", "Conexao localizada: " & workbookConnection.Name & " | Tipo=" & workbookConnection.Type

    On Error Resume Next
    Select Case workbookConnection.Type
        Case xlConnectionTypeOLEDB
            workbookConnection.OLEDBConnection.BackgroundQuery = False
            WriteLog "INFO", "POWER QUERY", "BackgroundQuery=False em OLEDBConnection"

        Case xlConnectionTypeODBC
            workbookConnection.ODBCConnection.BackgroundQuery = False
            WriteLog "INFO", "POWER QUERY", "BackgroundQuery=False em ODBCConnection"

        Case Else
            WriteLog "WARN", "POWER QUERY", "Tipo de conexao sem ajuste explicito de BackgroundQuery"
    End Select
    On Error GoTo TratarErro

    WriteLog "INFO", "POWER QUERY", "Iniciando atualizacao da consulta"
    workbookConnection.Refresh
    DoEvents

    On Error Resume Next
    Application.CalculateUntilAsyncQueriesDone
    On Error GoTo TratarErro

    WriteLog "INFO", "POWER QUERY", "Consulta atualizada com sucesso"
    Exit Sub

TratarErro:
    Dim errNum As Long, errSrc As String, errDesc As String
    errNum = Err.Number: errSrc = Err.Source: errDesc = Err.Description
    WriteLog "ERROR", "POWER QUERY", "Erro " & errNum & " - " & errDesc
    If errNum <> 0 Then Err.Raise errNum, errSrc, errDesc
End Sub

Private Function GetEmailSubject() As String
    GetEmailSubject = "Relatorio Semanal: Controle de Receitas Emitidas - " & Format$(Date, "dd/mm/yyyy")
End Function

Private Function GetRecipientTo() As String
    Dim configValue As String

    configValue = TryGetRecipientFromConfig()
    If Len(configValue) > 0 Then
        GetRecipientTo = configValue
        Exit Function
    End If

    If Len(DEFAULT_RECIPIENT_TO) > 0 Then
        WriteLog "WARN", "EMAIL", "Destinatario nao encontrado na tabela Config. Usando default."
    Else
        WriteLog "ERROR", "EMAIL", "Destinatario nao informado (config e default vazios)."
    End If

    GetRecipientTo = DEFAULT_RECIPIENT_TO
End Function

Private Function TryGetRecipientFromConfig() As String
    Dim ws As Worksheet
    Dim lo As ListObject
    Dim idx As Long
    Dim rawValue As String

    On Error GoTo TratarErro

    Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)
    If ws Is Nothing Then Exit Function

    Set lo = ws.ListObjects(CONFIG_TABLE_NAME)
    If lo Is Nothing Then Exit Function
    If lo.DataBodyRange Is Nothing Then Exit Function

    idx = ObterIndiceColunaPorSinonimos(lo, Array("PARA", "TO", "DESTINATARIO", "DESTINATARIO PRINCIPAL", "EMAIL"))
    If idx = 0 Then Exit Function

    rawValue = CStr(lo.DataBodyRange.Cells(1, idx).Value)
    rawValue = LimparEmails(rawValue)
    If Len(rawValue) > 0 Then
        TryGetRecipientFromConfig = rawValue
    End If
    Exit Function

TratarErro:
    TryGetRecipientFromConfig = vbNullString
End Function

Private Function ObterIndiceColunaPorSinonimos(ByVal lo As ListObject, ByVal sinonimos As Variant) As Long
    Dim i As Long
    Dim j As Long
    Dim nomeColuna As String
    Dim nomeSinonimo As String

    For i = 1 To lo.ListColumns.Count
        nomeColuna = NormalizarCabecalhoEmail(CStr(lo.ListColumns(i).Name))

        For j = LBound(sinonimos) To UBound(sinonimos)
            nomeSinonimo = NormalizarCabecalhoEmail(CStr(sinonimos(j)))
            If nomeColuna = nomeSinonimo Then
                ObterIndiceColunaPorSinonimos = i
                Exit Function
            End If
        Next j
    Next i
End Function

Private Function NormalizarCabecalhoEmail(ByVal textValue As String) As String
    Dim normalizedText As String

    normalizedText = NormalizarTexto(textValue)
    normalizedText = Replace(normalizedText, "_", " ")
    normalizedText = Replace(normalizedText, "-", " ")
    normalizedText = Replace(normalizedText, ".", " ")

    Do While InStr(1, normalizedText, "  ", vbBinaryCompare) > 0
        normalizedText = Replace(normalizedText, "  ", " ")
    Loop

    NormalizarCabecalhoEmail = Trim$(normalizedText)
End Function

Private Function LimparEmails(ByVal textValue As String) As String
    Dim cleaned As String

    cleaned = Trim$(textValue)
    If Len(cleaned) = 0 Then
        LimparEmails = vbNullString
        Exit Function
    End If

    cleaned = Replace(cleaned, " ", "")
    cleaned = Replace(cleaned, vbTab, "")
    cleaned = Replace(cleaned, vbCr, "")
    cleaned = Replace(cleaned, vbLf, "")
    LimparEmails = cleaned
End Function

Private Sub InitLog()
    Dim baseFolder As String

    baseFolder = LOG_FOLDER
    EnsureFolderExists baseFolder

    gLogFile = baseFolder & "\VBA_Internal.log"
    RotateLogFile gLogFile, LOG_MAX_LINES

    gLogReady = True

    WriteLog "INFO", "LOGGER", "Inicio da execucao VBA"
    WriteLog "INFO", "LOGGER", "Arquivo Excel: " & ThisWorkbook.FullName
End Sub

Private Sub EnsureFolderExists(ByVal folderPath As String)
    On Error GoTo TratarErro

    Dim parentPath As String

    If Len(folderPath) = 0 Then Exit Sub
    If Dir$(folderPath, vbDirectory) <> vbNullString Then Exit Sub

    If InStrRev(folderPath, "\") > 0 Then
        parentPath = Left$(folderPath, InStrRev(folderPath, "\") - 1)

        If Len(parentPath) > 0 Then
            If Dir$(parentPath, vbDirectory) = vbNullString Then
                EnsureFolderExists parentPath
            End If
        End If
    End If

    MkDir folderPath
    Exit Sub

TratarErro:
    Dim errNum As Long, errSrc As String, errDesc As String
    errNum = Err.Number: errSrc = Err.Source: errDesc = Err.Description
    If errNum <> 75 And errNum <> 76 Then
        Err.Raise errNum, errSrc, errDesc
    End If
End Sub

Private Sub RotateLogFile(ByVal filePath As String, ByVal maxLines As Long)
    On Error GoTo Finalizar

    Dim fileSystem As Object
    Dim textStream As Object
    Dim fileContent As String
    Dim linesArray() As String
    Dim lineIndex As Long
    Dim startLine As Long
    Dim newContent As String
    Dim totalLines As Long

    If maxLines <= 0 Then Exit Sub

    Set fileSystem = CreateObject("Scripting.FileSystemObject")

    If Not fileSystem.FileExists(filePath) Then Exit Sub

    Set textStream = fileSystem.OpenTextFile(filePath, 1, False, 0)
    fileContent = textStream.ReadAll
    textStream.Close
    Set textStream = Nothing

    If Len(fileContent) = 0 Then Exit Sub

    linesArray = Split(fileContent, vbCrLf)
    totalLines = UBound(linesArray) - LBound(linesArray) + 1

    If totalLines <= maxLines Then Exit Sub

    startLine = totalLines - maxLines
    newContent = vbNullString

    For lineIndex = startLine To UBound(linesArray)
        If Len(linesArray(lineIndex)) > 0 Then
            If Len(newContent) > 0 Then
                newContent = newContent & vbCrLf
            End If
            newContent = newContent & linesArray(lineIndex)
        End If
    Next lineIndex

    Set textStream = fileSystem.OpenTextFile(filePath, 2, True, 0)
    textStream.Write newContent
    textStream.Close

Finalizar:
    On Error Resume Next
    Set textStream = Nothing
    Set fileSystem = Nothing
End Sub

Private Sub WriteLog(ByVal logLevel As String, ByVal stepName As String, ByVal messageText As String)
    On Error GoTo Falha

    Dim fileNumber As Integer
    Dim execPrefix As String

    If Not gLogReady Then Exit Sub
    If gInLogWrite Then Exit Sub

    gInLogWrite = True

    If Len(mExecId) > 0 Then
        execPrefix = "[ExecId=" & mExecId & "] "
    Else
        execPrefix = vbNullString
    End If

    fileNumber = FreeFile

    Open gLogFile For Append As #fileNumber
    Print #fileNumber, Format$(Now, "dd/mm/yyyy hh:nn:ss") & _
                       " | VBA | " & SanitizarTextoLog(logLevel) & _
                       " | " & SanitizarTextoLog(stepName) & _
                       " | " & execPrefix & SanitizarTextoLog(messageText)
    Close #fileNumber
    gInLogWrite = False
    Exit Sub

Falha:
    On Error Resume Next
    If fileNumber <> 0 Then Close #fileNumber
    gInLogWrite = False
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
    texto = Replace(texto, ChrW$(8220), Chr$(34))
    texto = Replace(texto, ChrW$(8221), Chr$(34))
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

Private Sub FinalizeLog(Optional ByVal blnSucesso As Boolean = True)
    On Error GoTo TratarErro

    WriteLog "INFO", "LOGGER", "Fim da execucao VBA"
    WriteLog "INFO", "LOGGER", "FIM DO PROCESSO. Resultado=" & IIf(blnSucesso, "Sucesso", "Erro")
    Exit Sub

TratarErro:
    On Error Resume Next
    WriteLog "ERROR", "LOGGER", "FinalizeLog falhou. Err=" & Err.Number & " - " & Err.Description
    WriteLog "INFO", "LOGGER", "FIM DO PROCESSO. Resultado=Erro"
    On Error GoTo 0
End Sub

Private Sub LogarConexoesDisponiveis()
    Dim workbookConnection As workbookConnection
    Dim connectionCount As Long

    connectionCount = 0

    For Each workbookConnection In ThisWorkbook.Connections
        connectionCount = connectionCount + 1
        WriteLog "INFO", "CONEXAO", "Disponivel: " & workbookConnection.Name & " | Tipo=" & workbookConnection.Type
    Next workbookConnection

    If connectionCount = 0 Then
        WriteLog "WARN", "CONEXAO", "Nenhuma conexao encontrada em ThisWorkbook.Connections"
    End If
End Sub

' ====================================================================================
' SMOKE TEST - Executar via VBE sem disparar conexoes ou envio de e-mail
' ====================================================================================
Public Sub TestarLogger()
    Dim idSaida As String

    idSaida = NormalizeExecId("Teste ExecId #01 com espaco & acento!")
    mExecId = idSaida

    InitLog

    Debug.Print "=== TestarLogger: ModuloPrincipal ==="
    Debug.Print "ExecId : [" & mExecId & "]"
    Debug.Print "Log    : " & gLogFile

    WriteLog "INFO", "SMOKE", "Linha 1 - mensagem simples"
    WriteLog "INFO", "SMOKE", "Linha 2 - chars especiais: & < > ; -- SELECT 1"
    WriteLog "WARN", "SMOKE", "Linha 3 - nivel WARN"
    WriteLog "ERROR", "SMOKE", "Linha 4 - nivel ERROR"

    FinalizeLog True

    Debug.Print "Concluido. Verifique: " & gLogFile
End Sub
