# Runbook — OBs Paradas Fase (OBP-04)

## Diagnóstico rápido

```powershell
# Ver últimos logs
Get-Content "OBs Paradas Fase\Logs\*.log" -Tail 50

# Verificar sessão WhatsApp
Test-Path "lib\.wwebjs_auth\session-hub-global\Default\Local Storage\leveldb\*.log"
```

## Falhas comuns

### ExitCode=21 — Sessão expirada
```
lib\Authenticate-WhatsApp.bat
```
Escaneie o QR code. Aguarde "Cliente pronto" antes de fechar.

### ExitCode=24 — Chrome não inicializa
Verificar processos zumbi:
```powershell
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object { $_.CommandLine -like "*wwebjs_auth*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
Depois re-autenticar.

### ExitCode=3 — Oracle indisponível
Verificar conectividade com `SRVDB02`. Aguardar recovery automático (3 tentativas com backoff 30/60/120s).

### Mensagens na fila (ACK não confirmado)
Abrir Chrome virtual com sessão hub-global para drenar a fila:
```powershell
cd "C:\Automacoes\lib"
$env:NODE_PATH = "C:\Automacoes\Receitas Bloqueadas\node_modules"
node -e "const {Client,LocalAuth}=require('whatsapp-web.js');const c=new Client({authStrategy:new LocalAuth({dataPath:'.wwebjs_auth',clientId:'hub-global'}),puppeteer:{headless:false,args:['--no-sandbox']}});c.on('ready',()=>{console.log('Pronto');setTimeout(async()=>{await c.destroy();process.exit(0)},90000)});c.initialize()"
```
