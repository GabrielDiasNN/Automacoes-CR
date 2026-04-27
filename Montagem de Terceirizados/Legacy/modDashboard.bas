Attribute VB_Name = "modDashboard"
Option Explicit

' ====================================================================================
' ENTRY POINT
' ====================================================================================
Public Sub RegistrarHistorico(ByVal blnSucesso As Boolean, ByRef udtTel As Telemetria)
    Dim objWs      As Worksheet
    Dim lngUltima  As Long
    Dim dblTempo   As Double
    Dim dblTaxa    As Double

    On Error GoTo Falha

        Set objWs = Nothing
        On Error Resume Next
        Set objWs = ThisWorkbook.Worksheets("Dashboard")
        On Error GoTo Falha

            If objWs Is Nothing Then
                Set objWs = ThisWorkbook.Worksheets.Add(After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.count))
                objWs.Name = "Dashboard"
                CriarEstruturaDashboard objWs
            End If

            lngUltima = objWs.Cells(objWs.Rows.count, 1).End(xlUp).Row + 1
            If lngUltima > 59 Then
                objWs.Rows(10).Delete
                lngUltima = 59
            End If

            dblTempo = TimerElapsed(udtTel.InicioExecucao)

            If udtTel.totalLinhas > 0 Then
                dblTaxa = ((udtTel.totalLinhas - udtTel.totalErros) / udtTel.totalLinhas) * 100#
            Else
                dblTaxa = 100#
            End If

            With objWs
                .Cells(lngUltima, 1).Value = Now
                .Cells(lngUltima, 1).NumberFormat = "dd/mm/yyyy hh:mm:ss"
                .Cells(lngUltima, 1).HorizontalAlignment = xlCenter

                .Cells(lngUltima, 2).Value = IIf(blnSucesso, "S", "F")
                .Cells(lngUltima, 2).HorizontalAlignment = xlCenter

                .Cells(lngUltima, 3).Value = IIf(blnSucesso, "Sucesso", "Falha")
                .Cells(lngUltima, 3).HorizontalAlignment = xlCenter

                .Cells(lngUltima, 4).Value = udtTel.totalLinhas
                .Cells(lngUltima, 4).NumberFormat = "#,##0"
                .Cells(lngUltima, 4).HorizontalAlignment = xlCenter

                .Cells(lngUltima, 5).Value = udtTel.totalErros
                .Cells(lngUltima, 5).NumberFormat = "#,##0"
                .Cells(lngUltima, 5).HorizontalAlignment = xlCenter

                .Cells(lngUltima, 6).Value = dblTempo
                .Cells(lngUltima, 6).NumberFormat = "0.00"
                .Cells(lngUltima, 6).HorizontalAlignment = xlCenter

                .Cells(lngUltima, 7).Value = dblTaxa
                .Cells(lngUltima, 7).NumberFormat = "0.00"
                .Cells(lngUltima, 7).HorizontalAlignment = xlCenter

                .Cells(lngUltima, 8).Value = ROBO_VERSAO_DASH
                .Cells(lngUltima, 8).HorizontalAlignment = xlCenter

                If blnSucesso Then
                    .Rows(lngUltima).Interior.Color = RGB(198, 239, 206)
                Else
                    .Rows(lngUltima).Interior.Color = RGB(255, 199, 206)
                End If

                .Rows(lngUltima).RowHeight = 24
                .Range(.Cells(lngUltima, 1), .Cells(lngUltima, 8)).Borders.LineStyle = xlContinuous
                .Range("A10:A59").NumberFormat = "dd/mm/yyyy hh:mm:ss"
            End With

            AtualizarKPIsDashboard objWs
            AtualizarGraficoDashboard objWs
         Exit Sub

Falha:
            GravarLogEx "AVISO: RegistrarHistorico falhou: " & Err.Description, LOG_WARNING
End Sub

' ====================================================================================
' ESTRUTURA VISUAL
' ====================================================================================
Private Sub CriarEstruturaDashboard(ByVal ws As Worksheet)
    Dim blnScreenUpdatingOriginal As Boolean

    blnScreenUpdatingOriginal = Application.ScreenUpdating
    On Error GoTo TratarErro
        Application.ScreenUpdating = False

        With ws
            .Cells.Delete
            .Cells(1, 1).Value = "DASHBOARD DE MONITORAMENTO - " & ROBO_VERSAO_TEXTO
            .Cells(1, 1).Font.Size = 16
            .Cells(1, 1).Font.Bold = True
            .Cells(1, 1).Font.Color = RGB(255, 255, 255)
            .Range("A1:H1").Merge
            .Range("A1").HorizontalAlignment = xlCenter
            .Range("A1").VerticalAlignment = xlCenter
            .Rows(1).RowHeight = 38
            .Range("A1:H1").Interior.Color = RGB(31, 78, 120)

            .Rows(2).RowHeight = 5

            .Cells(3, 1).Value = ChrW(&H25B2) & " INDICADORES PRINCIPAIS"
            .Cells(3, 1).Font.Bold = True
            .Cells(3, 1).Font.Size = 11
            .Range("A3:H3").Merge
            .Range("A3").HorizontalAlignment = xlLeft
            .Range("A3:H3").Interior.Color = RGB(237, 125, 49)
            .Range("A3:H3").Font.Color = RGB(255, 255, 255)
            .Rows(3).RowHeight = 26

            .Cells(4, 1).Value = "Total Execu" & ChrW(&HE7) & ChrW(&HF5) & "es"
            .Cells(4, 3).Value = "Taxa de Sucesso"
            .Cells(4, 5).Value = "Tempo M" & ChrW(&HE9) & "dio"
            .Cells(4, 7).Value = ChrW(&HDA) & "ltima Execu" & ChrW(&HE7) & ChrW(&HE3) & "o"
            .Range("A4:B4").Merge
            .Range("C4:D4").Merge
            .Range("E4:F4").Merge
            .Range("G4:H4").Merge
            .Range("A4:H4").HorizontalAlignment = xlCenter
            .Range("A4:H4").Font.Bold = True
            .Range("A4:H4").Interior.Color = RGB(217, 225, 242)

            .Cells(5, 1).Value = "0"
            .Cells(5, 3).Value = "0.0%"
            .Cells(5, 5).Value = "0.00s"
            .Cells(5, 7).Value = "-"
            .Range("A5:B5").Merge
            .Range("C5:D5").Merge
            .Range("E5:F5").Merge
            .Range("G5:H5").Merge

            With .Range("A5:F5")
                .Font.Size = 20
                .Font.Bold = True
                .Font.Color = RGB(0, 102, 204)
                .HorizontalAlignment = xlCenter
            End With
            With .Range("G5:H5")
                .Font.Size = 16
                .Font.Bold = True
                .Font.Color = RGB(0, 102, 204)
                .HorizontalAlignment = xlCenter
            End With
            .Range("A4:H5").Borders.LineStyle = xlContinuous
            .Rows(4).RowHeight = 24
            .Rows(5).RowHeight = 48

            .Rows(6).RowHeight = 5

            .Cells(7, 1).Value = ChrW(&H25BA) & " HIST" & ChrW(&HD3) & "RICO DE EXECU" & ChrW(&HE7) & ChrW(&HF5) & "ES (" & ChrW(&HDA) & "ltimas 50)"
            .Cells(7, 1).Font.Bold = True
            .Cells(7, 1).Font.Size = 11
            .Range("A7:H7").Merge
            .Range("A7").HorizontalAlignment = xlLeft
            .Range("A7:H7").Interior.Color = RGB(68, 114, 196)
            .Range("A7:H7").Font.Color = RGB(255, 255, 255)
            .Rows(7).RowHeight = 26
            .Rows(8).RowHeight = 3

            .Cells(9, 1).Value = "Data/Hora"
            .Cells(9, 2).Value = "Status"
            .Cells(9, 3).Value = "Resultado"
            .Cells(9, 4).Value = "Linhas Proc."
            .Cells(9, 5).Value = "Erros"
            .Cells(9, 6).Value = "Tempo (s)"
            .Cells(9, 7).Value = "Taxa Acerto %"
            .Cells(9, 8).Value = "Vers" & ChrW(&HE3) & "o"
            With .Range("A9:H9")
                .Font.Bold = True
                .Font.Color = RGB(255, 255, 255)
                .Interior.Color = RGB(68, 114, 196)
                .HorizontalAlignment = xlCenter
                .Borders.LineStyle = xlContinuous
            End With
            .Rows(9).RowHeight = 26

            .Columns("A:A").ColumnWidth = 20
            .Columns("B:B").ColumnWidth = 9
            .Columns("C:C").ColumnWidth = 11
            .Columns("D:D").ColumnWidth = 13
            .Columns("E:E").ColumnWidth = 9
            .Columns("F:F").ColumnWidth = 11
            .Columns("G:G").ColumnWidth = 15
            .Columns("H:H").ColumnWidth = 9

            ' Removida dependencia de ActiveWindow
        End With

Saida:
        Application.ScreenUpdating = blnScreenUpdatingOriginal
        On Error GoTo 0
         Exit Sub

TratarErro:
            GravarLogEx "AVISO: CriarEstruturaDashboard falhou: " & Err.Description, LOG_WARNING
            Resume Saida
End Sub

' ====================================================================================
' KPIs
' ====================================================================================
Private Sub AtualizarKPIsDashboard(ByVal ws As Worksheet)
    Dim ultimaLinha As Long
    Dim totalExec   As Long
    Dim sucessos    As Long
    Dim somaTempos  As Double
    Dim mediaTempo  As Double
    Dim c           As Range

    On Error Resume Next

    ultimaLinha = ws.Cells(ws.Rows.count, 1).End(xlUp).Row
    If ultimaLinha < 10 Then Exit Sub

        totalExec = ultimaLinha - 9
        sucessos = 0
        somaTempos = 0#

        For Each c In ws.Range("C10:C" & ultimaLinha).Cells
            If CStr(c.Value) = "Sucesso" Then sucessos = sucessos + 1
            Next c
            For Each c In ws.Range("F10:F" & ultimaLinha).Cells
                If IsNumeric(c.Value) Then somaTempos = somaTempos + CDbl(c.Value)
                Next c

                If totalExec > 0 Then
                    mediaTempo = somaTempos / totalExec
                Else
                    mediaTempo = 0#
                End If

                ws.Cells(5, 1).Value = totalExec
                If totalExec > 0 Then
                    ws.Cells(5, 3).Value = Format$((sucessos / totalExec) * 100#, "0.0") & "%"
                Else
                    ws.Cells(5, 3).Value = "0.0%"
                End If
                ws.Cells(5, 5).Value = Format$(mediaTempo, "0.00") & "s"
                If IsDate(ws.Cells(ultimaLinha, 1).Value) Then
                    ws.Cells(5, 7).Value = Format$(CDate(ws.Cells(ultimaLinha, 1).Value), "dd/mm/yyyy hh:mm:ss")
                Else
                    ws.Cells(5, 7).Value = CStr(ws.Cells(ultimaLinha, 1).Value)
                End If

                On Error GoTo 0
End Sub

' ====================================================================================
' GRAFICO
' ====================================================================================
Private Sub AtualizarGraficoDashboard(ByVal ws As Worksheet)
    Dim ultimaLinha As Long
    Dim cht         As ChartObject
    Dim grafico     As ChartObject
    Dim serie1      As Series
    Dim serie2      As Series

    On Error Resume Next

    ultimaLinha = ws.Cells(ws.Rows.count, 1).End(xlUp).Row
    If ultimaLinha < 10 Then Exit Sub

        For Each cht In ws.ChartObjects
            cht.Delete
        Next cht

        Set grafico = ws.ChartObjects.Add( _
        Left:=ws.Range("J9").Left, Top:=ws.Range("J9").Top, Width:=450, Height:=280)

        With grafico.Chart
            .ChartType = xlLineMarkers
            Do While .SeriesCollection.count > 0
                .SeriesCollection(1).Delete
            Loop

            Set serie1 = .SeriesCollection.NewSeries
            With serie1
                .Name = "Quantidade de Erros"
                .Values = ws.Range("E10:E" & ultimaLinha)
                .XValues = ws.Range("A10:A" & ultimaLinha)
                .Format.line.ForeColor.RGB = RGB(192, 0, 0)
                .Format.line.Weight = 2.5
                .MarkerStyle = xlMarkerStyleCircle
                .MarkerSize = 6
                .AxisGroup = xlPrimary
            End With

            Set serie2 = .SeriesCollection.NewSeries
            With serie2
                .Name = "Taxa de Acerto %"
                .Values = ws.Range("G10:G" & ultimaLinha)
                .XValues = ws.Range("A10:A" & ultimaLinha)
                .Format.line.ForeColor.RGB = RGB(0, 176, 80)
                .Format.line.Weight = 2.5
                .MarkerStyle = xlMarkerStyleSquare
                .MarkerSize = 6
                .AxisGroup = xlSecondary
            End With

            .HasAxis(xlValue, xlSecondary) = True
            .Axes(xlValue, xlSecondary).MinimumScale = 0
            .Axes(xlValue, xlSecondary).MaximumScale = 100

            .HasTitle = True
            .ChartTitle.Text = ChrW(&H25B2) & " EVOLUCAO DE PERFORMANCE"
            .ChartTitle.Font.Size = 12
            .ChartTitle.Font.Bold = True
            .HasLegend = True
            .Legend.Position = xlLegendPositionBottom
        End With

        On Error GoTo 0
End Sub
