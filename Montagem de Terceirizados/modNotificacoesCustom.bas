Attribute VB_Name = "modNotificacoesCustom"
Option Explicit

' ====================================================================================
' PRIVADOS (ESTADO / CONFIG)
' ====================================================================================
Private Type EstadoSistemaDetalhado
    dtmSnapshot      As Date
    lngTotalLinhas   As Long
    lngTotalErros    As Long
    arrItensErro()   As DadosErro
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
Private Const LIMITE_ANOMALIA    As Long   = 50

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
    Dim blnAnomalia      As Boolean

    On Error GoTo TratarErro
    ProcessarNotificacoesCustomizadas = False

    GravarLogEx "Iniciando ProcessarNotificacoesCustomizadas (Plugin)", LOG_DEBUG

    ' 1. Snapshot do Estado
    With udtEstadoAtual
        .dtmSnapshot    = Now
        .lngTotalLinhas = lngTotalLinhas
        .lngTotalErros  = lngTotalErros
        .arrItensErro   = arrErros
        .strHashEstado  = GerarHashEstadoAtual(arrErros)
    End With

    ' 2. Carregar Cache e Comparar (Lógica Inteligente)
    ' udtEstadoAnterior = CarregarEstadoAnterior()
    ' udtMudancas = CompararEstados(udtEstadoAtual, udtEstadoAnterior)

    ' 3. Logica de anomalia
    blnAnomalia = (lngTotalErros >= LIMITE_ANOMALIA)
    If blnAnomalia Then
        GravarLogEx "ANOMALIA DETECTADA: Pico de erros (" & lngTotalErros & ")", LOG_WARNING
    End If

    ' 4. Persistencia
    SalvarEstadoCache udtEstadoAtual

    ProcessarNotificacoesCustomizadas = True
    GravarLogEx "ProcessarNotificacoesCustomizadas finalizado.", LOG_DEBUG
    Exit Function

TratarErro:
    GravarLogEx "ERRO no Plugin de Notificacao: " & Err.Description, LOG_ERROR
End Function

' ====================================================================================
' INTERNOS / AUXILIARES
' ====================================================================================
Private Function GerarHashEstadoAtual(ByRef arr() As DadosErro) As String
    Dim lngI    As Long
    Dim strBase As String
    
    On Error Resume Next
    strBase = ""
    For lngI = LBound(arr) To UBound(arr)
        strBase = strBase & arr(lngI).NumOB & "|" & arr(lngI).detalheErro
        If Len(strBase) > 5000 Then Exit For
    Next lngI
    
    GerarHashEstadoAtual = GerarHashDJB2(strBase)
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

Private Function GerarHashDJB2(ByVal texto As String) As String
    Dim i As Long
    Dim h As Double ' Usar Double para evitar overflow em somas grandes antes do And
    h = 5381
    For i = 1 To Len(texto)
        ' h = ((h * 33) + AscW(Mid$(texto, i, 1)))
        ' No VBA, DJB2 simplificado para 32-bit:
        h = ((h * 33) + AscW(Mid$(texto, i, 1)))
        ' Simula 32-bit (aproximado para strings curtas)
        If h > 2147483647 Then h = h Mod 2147483647
    Next i
    GerarHashDJB2 = CStr(Int(h))
End Function
