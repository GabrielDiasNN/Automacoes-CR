Option Explicit

Dim wsh, cmdExe, comandoBat, batPath, execId

Set wsh = CreateObject("WScript.Shell")
cmdExe = wsh.ExpandEnvironmentStrings("%ComSpec%")

batPath = "C:\Automacoes\Receitas Bloqueadas\RunWhatsApp.bat"
execId = "UNIT_TEST_QUOTE"

' Testando exatamente a linha do Step 191:
comandoBat = """" & cmdExe & """ /c """"" & batPath & """ """ & execId & """ AUTO"""

WScript.Echo "Comando a executar:"
WScript.Echo comandoBat

Dim rc
rc = wsh.Run(comandoBat, 0, True)

WScript.Echo "ExitCode=" & rc
WScript.Quit rc
