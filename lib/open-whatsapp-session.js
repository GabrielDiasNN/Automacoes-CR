// Abre o Chrome com a sessao hub-global em modo visivel e mantem aberto ate Ctrl+C.
// Uso: node open-whatsapp-session.js [clientId]
const { Client, LocalAuth } = require('whatsapp-web.js');
const { resolveAuthPath } = require('./whatsapp-auth-path');
const {
    sessaoPersistidaAusente: sessaoAusenteEmDisco,
    sessaoPersistidaConfirmada: sessaoConfirmadaEmDisco
} = require('./whatsapp-session-state');

const CLIENT_ID = process.argv[2] || 'hub-global';
const AUTH_PATH = resolveAuthPath();

// Mesmo contrato de WhatsApp-Core.js — modulo unico, para os dois runtimes nao divergirem.
function sessaoPersistidaAusente() {
    return sessaoAusenteEmDisco(AUTH_PATH, CLIENT_ID);
}

// Nao e a negacao da funcao acima: um erro de leitura do perfil devolve false nas DUAS.
// Aqui isso e proposital — sem confirmacao positiva o operador continua esperando.
function sessaoPersistidaConfirmada() {
    return sessaoConfirmadaEmDisco(AUTH_PATH, CLIENT_ID);
}

function log(nivel, msg) {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    const ts = `${p(d.getDate())}/${p(d.getMonth()+1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
    console.log(`[${ts}] [${nivel}] ${msg}`);
}

const client = new Client({
    authStrategy: new LocalAuth({ dataPath: AUTH_PATH, clientId: CLIENT_ID }),
    takeoverOnConflict: true,
    puppeteer: {
        headless: false,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    }
});

client.on('qr', () => {
    log('WARN', 'QR Code recebido — sessao expirada. Escaneie com o celular para reautenticar.');
});

client.on('loading_screen', (pct, msg) => {
    log('INFO', `Carregando: ${pct}% - ${msg}`);
});

client.on('authenticated', () => {
    log('INFO', 'Sessao autenticada.');
});

client.on('ready', async () => {
    log('INFO', '=================================================');
    log('INFO', `Sessao "${CLIENT_ID}" pronta — navegador aberto.`);

    // 'ready' nao garante sessao gravada em disco: o WhatsApp Web ainda esta escrevendo
    // as chaves no IndexedDB do perfil. Encerrar aqui produz uma sessao que nao sobrevive
    // ao proximo processo — foi o que se observou em 28/07/2026. Confirma antes de liberar.
    if (!sessaoPersistidaConfirmada()) {
        log('INFO', 'Gravando sessao em disco... NAO encerre nem feche o navegador agora.');
        for (let esperado = 0; esperado < 60000; esperado += 3000) {
            await new Promise(r => setTimeout(r, 3000));
            if (sessaoPersistidaConfirmada()) { break; }
        }
        if (!sessaoPersistidaConfirmada()) {
            log('WARN', 'Sessao ainda NAO confirmada em disco apos 60s. Mantenha esta janela aberta');
            log('WARN', 'por mais alguns minutos — encerrar agora exigira novo QR Code.');
        } else {
            log('INFO', 'Sessao gravada em disco — ja sobrevive a novas execucoes.');
        }
    } else {
        log('INFO', 'Sessao persistida em disco confirmada.');
    }

    log('INFO', 'Envie as mensagens pendentes e feche quando terminar.');
    log('INFO', 'Para encerrar: Ctrl+C nesta janela (nao feche o Chrome direto).');
    log('INFO', '=================================================');
});

client.on('disconnected', (reason) => {
    log('WARN', `Desconectado: ${reason}`);
});

async function encerrar() {
    log('INFO', 'Encerrando sessao...');
    try { await client.destroy(); } catch (_) {}
    process.exit(0);
}

process.on('SIGINT',  encerrar);
process.on('SIGTERM', encerrar);

log('INFO', `Iniciando sessao "${CLIENT_ID}" em modo visivel...`);

// Sem sessao o script ainda serve: o Chrome abre visivel e o proprio WhatsApp Web
// apresenta o QR Code. So avisa o operador do que esperar — e do que NAO fazer, porque
// o evento 'ready' nao significa sessao gravada em disco (ver o handler de 'ready').
if (sessaoPersistidaAusente()) {
    log('WARN', `Sessao "${CLIENT_ID}" ausente ou zerada (dispositivo desvinculado / logout).`);
    log('WARN', 'O QR Code sera exibido no navegador. Escaneie: WhatsApp > Aparelhos conectados.');
    log('WARN', 'Depois de conectar, AGUARDE a confirmacao de sessao gravada antes de encerrar.');
}

client.initialize().catch(async (err) => {
    log('ERROR', `Falha ao inicializar: ${err.message}`);
    if (/Execution context was destroyed/i.test(String(err && err.message))) {
        log('ERROR', 'Perfil do Chrome inconsistente. Feche janelas abertas desta sessao;');
        log('ERROR', 'se persistir, reautentique com lib\\Authenticate-WhatsApp.bat.');
    }
    try { await client.destroy(); } catch (_) {}
    process.exit(1);
});
