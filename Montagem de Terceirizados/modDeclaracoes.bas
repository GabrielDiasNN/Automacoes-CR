Attribute VB_Name = "modDeclaracoes"
Option Explicit

' =========================
' API Windows
' =========================
#If VBA7 Then
    Public Declare PtrSafe Function GetAsyncKeyState Lib "user32" (ByVal vKey As Long) As Integer
#Else
    Public Declare Function GetAsyncKeyState Lib "user32" (ByVal vKey As Long) As Integer
#End If

' =========================
' Types
' =========================
Public Type ConfiguracaoAplicacao
    ScreenUpdating  As Boolean
    EnableEvents    As Boolean
    Calculation     As Long
    DisplayAlerts   As Boolean
    ConfiguradoOK   As Boolean
End Type

Public Type DadosErro
    SitOB       As Variant
    Progr       As Variant
    Faccao      As Variant
    pcsProg     As Variant
    NumOB       As Variant
    Kanban      As Variant
    refCliente  As String
    qtpcnf      As String
    ObsOB       As String
    detalheErro As String
    Alternativo As String
    FaseAtual   As Variant
    StatusFase  As Variant
    DtUltConf   As Variant
End Type

Public Type Telemetria
    InicioExecucao As Double
    FimConexao     As Double
    FimValidacao   As Double
    FimEmail       As Double
    totalLinhas    As Long
    totalErros     As Long
End Type

' =========================
' Enum
' =========================
Public Enum NivelLog
    LOG_DEBUG   = 0
    LOG_INFO    = 1
    LOG_WARNING = 2
    LOG_ERROR   = 3
End Enum

' =========================
' Versao
' =========================
Public Const ROBO_VERSAO_NUM   As String = "8.8.0"
Public Const ROBO_VERSAO_TEXTO As String = "8.8.0 FINAL"
Public Const ROBO_VERSAO_DASH  As String = "v8.8.0"

' =========================
' Oracle / Stamp
' =========================
Public Const ORACLE_TIMEOUT_SECONDS   As Long = 600
Public Const STAMP_MAX_TENTATIVAS     As Long = 3
Public Const STAMP_RETRY_WAIT_SECONDS As Long = 2
Public Const STAMP_TABLE_NAME         As String = "VW_EXC_OB_PED_ROM_Faccao"
Public Const STAMP_COLUMN_HEADER      As String = "VALIDA_ATUALIZACAO"
Public Const STAMP_NAMED_RANGE        As String = "RoboRefreshStamp"

' =========================
' Colunas Oracle
' =========================
Public Const C_REF_CLIENTE    As String = "CD_REF_CLT"
Public Const C_QT_PC_NF       As String = "QT_PC_NF"
Public Const C_OBS_OB         As String = "OBS_OB"
Public Const C_NUM_OB         As String = "NR_OB"
Public Const C_SIT_OB         As String = "ST_OB_ABERTO"
Public Const C_PROGR          As String = "NR_PROG"
Public Const C_FACCAO         As String = "DS_ITEMPED_CLT"
Public Const C_PCS_PROG       As String = "QT_PC_PROG"
Public Const C_KANBAN         As String = "NR_KANBAN"
Public Const C_ALTERNATIVO    As String = "CD_ALTERNATIVO"
Public Const C_FASE_ATUAL     As String = "DS_FASE_ATUAL"
Public Const C_ST_FASE        As String = "DS_ST_FASE_ATUAL"
Public Const C_DT_ULT_CONF    As String = "DT_ULT_CONFIRMACAO"
Public Const C_OUTPUT_VAL     As String = "VALIDACAO_NF"
Public Const NUM_COLUNAS_ERRO As Long = 14

' =========================
' Email / Retry
' =========================
Public Const MAX_EMAIL_RETRIES As Integer = 3
Public Const RETRY_DELAY_BASE  As Integer = 2

' =========================
' HTML Icons
' =========================
Public Const HTML_ICON_WARNING   As String = "&#9888;&#65039;"
Public Const HTML_ICON_CHECK     As String = "&#9989;"
Public Const HTML_ICON_ROBOT     As String = "&#129302;"
Public Const HTML_ICON_CALENDAR  As String = "&#128197;"
Public Const HTML_ICON_MAGNIFY   As String = "&#128269;"
Public Const HTML_ICON_PACKAGE   As String = "&#128230;"
Public Const HTML_ICON_CHART     As String = "&#128202;"
Public Const HTML_ICON_CROSS     As String = "&#10060;"
Public Const HTML_ICON_STOPWATCH As String = "&#9201;"
Public Const HTML_ICON_TROPHY    As String = "&#127942;"
Public Const HTML_ICON_TARGET    As String = "&#127919;"
Public Const HTML_ICON_CHART_UP  As String = "&#128200;"
Public Const HTML_ICON_FIRE      As String = "&#128293;"

' =========================
' Log
' =========================
Public Const LOG_MIN_LEVEL         As Long   = 0
Public Const LOG_MAX_BYTES         As Long   = 2097152
Public Const LOG_MAX_BACKUPS       As Long   = 5
Public Const LOG_SEPARADOR_DUPLO   As String = "================================================================================"
Public Const LOG_SEPARADOR_SIMPLES As String = "--------------------------------------------------------------------------------"
Public Const LOG_PATH_PADRAO       As String = "C:\Automacoes\Montagem de Terceirizados\Logs\VBA_Internal.log"