@echo off
chcp 65001 >nul
TITLE MODO DEBUG - MONITOR DE AUTOMACOES
COLOR 0E
CLS

ECHO ========================================================
ECHO INICIANDO EM MODO DEBUG
ECHO ========================================================
ECHO.
ECHO Se houver um erro, ele aparecera em VERMELHO abaixo.
ECHO.

powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File "C:\Automacoes\MonitorAutomacoes.ps1"

ECHO.
ECHO ========================================================
ECHO O script parou. Se voce ve esta mensagem, algo aconteceu.
ECHO ========================================================
PAUSE