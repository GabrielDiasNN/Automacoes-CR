Attribute VB_Name = "clsAppContext"
VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
End
Option Explicit

' ====================================================================================
' Entidade: clsAppContext
' Descricao: Carrega o estado e as configuracoes globais da execucao.
' ====================================================================================

Private pWorkbookAlvo As Workbook
Private pWsBase As Worksheet
Private pModoRobo As Boolean
Private pRunId As String
Private pOutlookAdapter As ClsOutlookAdapter
Private pEmailComposerService As ClsEmailComposerService

' Estado original do Excel para restauracao
Private pScreenUpdatingOriginal As Boolean
Private pEnableEventsOriginal As Boolean
Private pDisplayAlertsOriginal As Boolean
Private pCalculationOriginal As XlCalculation

Public Property Get WorkbookAlvo() As Workbook
    Set WorkbookAlvo = pWorkbookAlvo
End Property

Public Property Set WorkbookAlvo(ByVal wbValor As Workbook)
    Set pWorkbookAlvo = wbValor
End Property

Public Property Get WsBase() As Worksheet
    Set WsBase = pWsBase
End Property

Public Property Set WsBase(ByVal wsValor As Worksheet)
    Set pWsBase = wsValor
End Property

Public Property Get ModoRobo() As Boolean
    ModoRobo = pModoRobo
End Property

Public Property Let ModoRobo(ByVal blnValor As Boolean)
    pModoRobo = blnValor
End Property

Public Property Get RunId() As String
    RunId = pRunId
End Property

Public Property Let RunId(ByVal strValor As String)
    pRunId = strValor
End Property

' Getters/Setters para estado do Excel
Public Property Get ScreenUpdatingOriginal() As Boolean
    ScreenUpdatingOriginal = pScreenUpdatingOriginal
End Property

Public Property Let ScreenUpdatingOriginal(ByVal blnValor As Boolean)
    pScreenUpdatingOriginal = blnValor
End Property

Public Property Get EnableEventsOriginal() As Boolean
    EnableEventsOriginal = pEnableEventsOriginal
End Property

Public Property Let EnableEventsOriginal(ByVal blnValor As Boolean)
    pEnableEventsOriginal = blnValor
End Property

Public Property Get DisplayAlertsOriginal() As Boolean
    DisplayAlertsOriginal = pDisplayAlertsOriginal
End Property

Public Property Let DisplayAlertsOriginal(ByVal blnValor As Boolean)
    pDisplayAlertsOriginal = blnValor
End Property

Public Property Get CalculationOriginal() As XlCalculation
    CalculationOriginal = pCalculationOriginal
End Property

Public Property Let CalculationOriginal(ByVal enmValor As XlCalculation)
    pCalculationOriginal = enmValor
End Property

Public Property Get OutlookAdapter() As ClsOutlookAdapter
    If pOutlookAdapter Is Nothing Then
        Set pOutlookAdapter = New ClsOutlookAdapter
    End If

    Set OutlookAdapter = pOutlookAdapter
End Property

Public Property Get EmailComposerService() As ClsEmailComposerService
    If pEmailComposerService Is Nothing Then
        Set pEmailComposerService = New ClsEmailComposerService
    End If

    Set EmailComposerService = pEmailComposerService
End Property

Public Sub ResetInfraDependencies()
    On Error Resume Next

    If Not pOutlookAdapter Is Nothing Then
        pOutlookAdapter.ResetState
    End If

    Set pOutlookAdapter = Nothing
    Set pEmailComposerService = Nothing
End Sub
