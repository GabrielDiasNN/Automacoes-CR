@echo off
REM { "version": "1.1.0", "description": "Autenticador central da sessao hub-global do WhatsApp" }
REM Use este arquivo sempre que precisar re-autenticar o WhatsApp para qualquer automacao
REM que utilize clientId "hub-global" (OBs Paradas Fase, Receitas Bloqueadas, etc.)
SetLocal
cd /d "%~dp0"
REM Daemon WhatsApp vivo segura o perfil hub-global: nao autenticar por cima dele (ver Lib-WhatsAppBatch.psm1).
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Import-Module '%~dp0Lib-WhatsAppBatch.psm1' -Force; try { if (@(Get-WhatsAppDaemonProcess).Count -gt 0) { exit 2 }; exit 0 } catch { exit 1 }"
if errorlevel 2 goto daemon_ativo
if errorlevel 1 goto verificacao_falhou
goto segue
:daemon_ativo
echo Daemon WhatsApp ativo no perfil hub-global. Pare o processo node do whatsapp-daemon.js antes de reautenticar.
pause
exit /b 2
:verificacao_falhou
echo Nao foi possivel verificar o daemon WhatsApp. Autenticacao abortada por seguranca.
pause
exit /b 1
:segue
set NODE_PATH=%~dp0node_modules
echo Iniciando autenticacao WhatsApp (sessao hub-global)...
echo Escaneie o QR code com o celular: WhatsApp ^> Aparelhos conectados ^> Conectar um aparelho
echo.
node "WhatsApp-Core.js" "AUTH-HUB-GLOBAL" "VISUAL" "hub-global" "" "" ""
pause
