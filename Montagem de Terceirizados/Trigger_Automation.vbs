' ============================================================================================
' EXECUTOR OTIMIZADO DO ROBO FISCAL (Versão Produção v2.1)
' ============================================================================================
' Alterações:
' - Detecção de fim de processo em tempo real (Sincronizado com VBA)
' - Timeout configurável
' - Correção de detecção de versão no histórico de logs
' ============================================================================================

Option Explicit

Dim xlApp, xlBook, fso
Dim caminhoArquivo, logPath, logVBA
Dim inicioExecucao, fimExecucao
Dim sucesso, mensagemErro
Dim roboVersao

' ========== CONFIGURAÇÕES (Editáveis) ==========
Const TIMEOUT_MAXIMO = 300              ' Segundos (5 minutos)
Const INTERVALO_VERIFICACAO = 3000      ' Milissegundos (3s)
Const TEMPO_INATIVIDADE_CRITICO = 30    ' Segundos sem mudança no log = possível travamento

caminhoArquivo = "C:\Automacoes\Montagem de Terceirizados\Validador_Notas_Montagem.xlsm"
logPath = "C:\Automacoes\Montagem de Terceirizados\Logs\Execution.log"
logVBA = "C:\Automacoes\Montagem de Terceirizados\Logs\VBA_Internal.log"

Set fso = CreateObject("Scripting.FileSystemObject")
inicioExecucao = Now
sucesso = False
mensagemErro = ""
roboVersao = "(aguardando)"

Call CriarLogSeNaoExistir(logPath)
Call CriarLogSeNaoExistir(logVBA)

Call WriteLog("INFO", "================================================================================")
Call WriteLog("INFO", "INICIO - Robo Fiscal " & roboVersao)
Call WriteLog("INFO", "================================================================================")

' ========== VALIDAÇÕES INICIAIS ==========
If Not fso.FileExists(caminhoArquivo) Then
    Call WriteLog("ERRO", "Arquivo nao encontrado: " & caminhoArquivo)
    WScript.Quit 1
End If

Dim tamanhoInicial, tamanhoAnterior
tamanhoInicial = 0
If fso.FileExists(logVBA) Then
    tamanhoInicial = fso.GetFile(logVBA).Size
    Call WriteLog("INFO", "Log VBA inicial: " & tamanhoInicial & " bytes")
    
    ' Tenta identificar versão da execução anterior para referência
    Dim conteudoExistente, vTemp
    conteudoExistente = LerUltimasLinhas(logVBA, 20)
    vTemp = ExtrairVersao(conteudoExistente)
    If vTemp <> "" Then
        roboVersao = vTemp
        Call WriteLog("INFO", "Versao detectada (historico): " & roboVersao)
    End If
End If
tamanhoAnterior = tamanhoInicial

' ========== INICIALIZAÇÃO EXCEL ==========
On Error Resume Next
Set xlApp = CreateObject("Excel.Application")
If Err.Number <> 0 Then
    Call WriteLog("ERRO", "ERRO ao criar Excel: " & Err.Description)
    WScript.Quit 1
End If
On Error Goto 0

xlApp.Visible = False
xlApp.DisplayAlerts = False
xlApp.ScreenUpdating = False

Call WriteLog("INFO", "Excel iniciado (invisivel)")

On Error Resume Next
Set xlBook = xlApp.Workbooks.Open(caminhoArquivo)
If Err.Number <> 0 Then
    Call WriteLog("ERRO", "ERRO ao abrir workbook: " & Err.Description)
    xlApp.Quit
    Set xlApp = Nothing
    WScript.Quit 2
End If
On Error Goto 0

Call WriteLog("INFO", "Workbook aberto (" & xlBook.Worksheets.Count & " abas)")

' ========== EXECUÇÃO DA MACRO ==========
Call WriteLog("INFO", "Executando AtualizarEValidar(True)...")

On Error Resume Next
xlApp.Run "AtualizarEValidar", True

If Err.Number <> 0 Then
    mensagemErro = "Erro ao executar macro: " & Err.Description
    Call WriteLog("ERRO", mensagemErro)
    xlBook.Close False
    xlApp.Quit
    Set xlBook = Nothing
    Set xlApp = Nothing
    WScript.Quit 3
Else
    Call WriteLog("INFO", "Macro disparada com sucesso")
End If
On Error Goto 0

' ========== MONITORAMENTO OTIMIZADO ==========
Call WriteLog("INFO", "Aguardando VBA finalizar (timeout: " & TIMEOUT_MAXIMO & "s)...")

Dim tempoInicio, encontrouFim, conteudoNovo, tamanhoAtual
Dim ultimaMudancaLog, segundosDecorridos
Dim v

tempoInicio = Timer
ultimaMudancaLog = Timer
encontrouFim = False

Do While Not encontrouFim And (Timer - tempoInicio) < TIMEOUT_MAXIMO
    
    If fso.FileExists(logVBA) Then
        On Error Resume Next
        tamanhoAtual = fso.GetFile(logVBA).Size
        
        ' Detecta se o log cresceu (VBA está ativo)
        If tamanhoAtual > tamanhoAnterior Then
            ultimaMudancaLog = Timer
            conteudoNovo = LerArquivoAposBytes(logVBA, tamanhoInicial) ' Lê tudo desde o início da exec
            
            ' Detectar versão (atualiza se encontrar uma nova)
            v = ExtrairVersao(conteudoNovo)
            If v <> "" And v <> roboVersao Then
                roboVersao = v
                ' Call GravarLog("Versao atualizada: " & roboVersao) ' Opcional: descomentar para debug
            End If
            
            ' Detectar conclusão
            If InStr(conteudoNovo, "FIM DO PROCESSO.") > 0 Then
                encontrouFim = True
                
                If InStr(conteudoNovo, "Resultado=Sucesso") > 0 Then
                    sucesso = True
                    Call WriteLog("INFO", "VBA finalizou com SUCESSO (v" & roboVersao & ")")
                Else
                    sucesso = False
                    Call WriteLog("INFO", "VBA finalizou com ERRO (v" & roboVersao & ")")
                End If
                Exit Do
            ElseIf InStr(conteudoNovo, "ERRO FATAL") > 0 Then
                encontrouFim = True
                sucesso = False
                Call WriteLog("ERRO", "VBA reportou ERRO FATAL (v" & roboVersao & ")")
                Exit Do
            End If
            
            tamanhoAnterior = tamanhoAtual
        End If
        
        On Error Goto 0
    End If
    
    ' Detecta travamento (log parou de crescer)
    If (Timer - ultimaMudancaLog) > TEMPO_INATIVIDADE_CRITICO Then
        Call WriteLog("WARN", "AVISO: Log VBA sem mudanca ha " & Int(Timer - ultimaMudancaLog) & "s")
        ultimaMudancaLog = Timer ' Reset para evitar spam
    End If
    
    ' Log de progresso a cada 15 segundos
    segundosDecorridos = Int(Timer - tempoInicio)
    If segundosDecorridos Mod 15 = 0 And segundosDecorridos > 0 Then
        Call WriteLog("INFO", "Aguardando... " & segundosDecorridos & "s")
        WScript.Sleep INTERVALO_VERIFICACAO + 1000 ' Evita log duplicado
    Else
        WScript.Sleep INTERVALO_VERIFICACAO
    End If
Loop

If Not encontrouFim Then
    Call WriteLog("TIMEOUT", "TIMEOUT: VBA nao finalizou em " & TIMEOUT_MAXIMO & "s")
    sucesso = False
End If

' ========== FINALIZAÇÃO ==========
If sucesso Then
    On Error Resume Next
    xlBook.Save
    If Err.Number <> 0 Then
        Call WriteLog("WARN", "AVISO: Erro ao salvar: " & Err.Description)
    Else
        Call WriteLog("INFO", "Arquivo salvo")
    End If
    On Error Goto 0
End If

Call WriteLog("INFO", "Fechando Excel...")
xlBook.Close False
xlApp.Quit

Set xlBook = Nothing
Set xlApp = Nothing

fimExecucao = Now
Dim tempoTotal, statusFinal, codigoSaida
tempoTotal = DateDiff("s", inicioExecucao, fimExecucao)

If encontrouFim Then
    statusFinal = "SUCESSO"
    codigoSaida = 0
Else
    statusFinal = "TIMEOUT"
    codigoSaida = 5
End If

Call WriteLog("INFO", "================================================================================")
Call WriteLog("INFO", "FIM - Tempo: " & tempoTotal & "s | Status: " & statusFinal & " | Versao: " & roboVersao)
Call WriteLog("INFO", "================================================================================")

WScript.Quit codigoSaida

' ========== FUNÇÕES AUXILIARES ==========

Sub CriarLogSeNaoExistir(caminho)
    On Error Resume Next
    If Not fso.FileExists(caminho) Then
        Dim objFile
        Set objFile = fso.CreateTextFile(caminho, True)
        objFile.Close
        Set objFile = Nothing
    End If
End Sub

Sub WriteLog(level, msg)
    On Error Resume Next
    Dim agora, ts, objFile
    agora = Now
    ts = Right("00" & Day(agora), 2) & "/" & Right("00" & Month(agora), 2) & "/" & Year(agora) & " " & _
         Right("00" & Hour(agora), 2) & ":" & Right("00" & Minute(agora), 2) & ":" & Right("00" & Second(agora), 2)
    
    Set objFile = fso.OpenTextFile(logPath, 8, True)
    objFile.WriteLine ts & " [VBS] [" & level & "] " & msg
    objFile.Close
    Set objFile = Nothing
End Sub

Function LerArquivoAposBytes(caminho, bytesIniciais)
    On Error Resume Next
    Dim objFile, conteudoCompleto
    
    Set objFile = fso.OpenTextFile(caminho, 1)
    conteudoCompleto = objFile.ReadAll
    objFile.Close
    
    If Len(conteudoCompleto) > bytesIniciais Then
        LerArquivoAposBytes = Mid(conteudoCompleto, bytesIniciais + 1)
    Else
        LerArquivoAposBytes = ""
    End If
End Function

Function LerUltimasLinhas(caminho, numLinhas)
    On Error Resume Next
    Dim objFile, arrLinhas, i, resultado, conteudo
    
    Set objFile = fso.OpenTextFile(caminho, 1)
    If Not objFile.AtEndOfStream Then
        conteudo = objFile.ReadAll
        objFile.Close
        
        arrLinhas = Split(conteudo, vbCrLf)
        resultado = ""
        
        Dim inicio
        inicio = UBound(arrLinhas) - numLinhas
        If inicio < 0 Then inicio = 0
        
        For i = inicio To UBound(arrLinhas)
            resultado = resultado & arrLinhas(i) & vbCrLf
        Next
        
        LerUltimasLinhas = resultado
    Else
        objFile.Close
        LerUltimasLinhas = ""
    End If
End Function

Function ExtrairVersao(texto)
    On Error Resume Next
    Dim re, m
    Set re = CreateObject("VBScript.RegExp")
    
    ' Padrão: "Versão: 8.8.0" (aceita "Versao" ou "Versão")
    re.Pattern = "Vers[aã]o:\s*([^\r\n\|]+)"
    re.IgnoreCase = True
    re.Global = False
    
    If re.Test(texto) Then
        Set m = re.Execute(texto)
        ExtrairVersao = Trim(m(0).SubMatches(0))
    Else
        ExtrairVersao = ""
    End If
End Function