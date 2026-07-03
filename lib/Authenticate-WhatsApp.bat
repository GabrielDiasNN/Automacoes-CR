@echo off
REM { "version": "1.1.0", "description": "Autenticador central da sessao hub-global do WhatsApp" }
REM Use este arquivo sempre que precisar re-autenticar o WhatsApp para qualquer automacao
REM que utilize clientId "hub-global" (OBs Paradas Fase, Receitas Bloqueadas, etc.)
SetLocal
cd /d "%~dp0"
set NODE_PATH=%~dp0node_modules
echo Iniciando autenticacao WhatsApp (sessao hub-global)...
echo Escaneie o QR code com o celular: WhatsApp ^> Aparelhos conectados ^> Conectar um aparelho
echo.
node "WhatsApp-Core.js" "AUTH-HUB-GLOBAL" "VISUAL" "hub-global" "" "" ""
pause
