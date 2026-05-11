@echo off
:: Hub Soberano v5.1.0 - Enterprise Access Script
:: Garantindo caminhos absolutos e robustez operacional

SET APP_ROOT=C:\Automacoes
SET VENV_PYTHON=%APP_ROOT%\.venv\Scripts\python.exe
SET API_PORT=8000
SET URL=http://localhost:8000/dashboard/

echo [INFO] Verificando Hub Soberano na porta %API_PORT%...

:: Tenta verificar se a porta ja esta aberta
netstat -ano | findstr ":%API_PORT%" > nul
if %errorlevel% == 0 (
    echo [OK] Servidor ja esta ativo.
) else (
    echo [WARN] Servidores offline. Iniciando...
    
    :: Iniciar API (Uvicorn)
    cd /d "%APP_ROOT%\Orchestrator"
    start /min "Orchestrator_API" "%VENV_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    
    :: Iniciar Worker
    start /min "Orchestrator_Worker" "%VENV_PYTHON%" worker.py
    
    echo [INFO] Aguardando 5 segundos para estabilizacao...
    timeout /t 5 /nobreak > nul
)

echo [DONE] Abrindo Dashboard no navegador...
start "" "%URL%"
exit
