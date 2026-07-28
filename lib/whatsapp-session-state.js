// Fonte unica da deteccao de "sessao do WhatsApp ausente/zerada".
// A sessao autenticada do WhatsApp Web vive no IndexedDB do perfil Chrome persistido
// pelo LocalAuth. Quando o dispositivo e desvinculado (evento 'disconnected' com razao
// LOGOUT), essa base e zerada: sobram apenas CURRENT/LOG, sem MANIFEST-* nem .ldb/.log.
// Nesse estado o WhatsApp Web navega para a tela de QR durante o bootstrap e o Puppeteer
// estoura "Execution context was destroyed" — erro que PARECE transiente.
//
// Vive em modulo proprio pelo mesmo motivo de whatsapp-auth-path.js: mais de um consumidor
// (WhatsApp-Core.js e open-whatsapp-session.js) precisa da MESMA resposta. Duas copias que
// divergem significam um motor abortando por sessao ausente enquanto o outro tenta abrir,
// ou o inverso — sem sinal de erro que denuncie a divergencia.
//
// Sao DUAS perguntas de sinal oposto, e um booleano so nao responde as duas: quem decide
// ABORTAR antes do bootstrap trata a duvida como "prossiga" (nao derrubar automacao por
// erro de leitura), enquanto quem CONFIRMA a gravacao da sessao trata a mesma duvida como
// "ainda nao confirmado" (encerrar cedo descarta as chaves e a proxima execucao pede QR).
// Dai o estado ternario: cada consumidor escolhe o lado seguro do SEU fluxo.
const fs = require('fs');
const path = require('path');

const ESTADO_AUSENTE       = 'AUSENTE';
const ESTADO_PRESENTE      = 'PRESENTE';
const ESTADO_INDETERMINADO = 'INDETERMINADO';

// authPath: raiz do LocalAuth (resolveAuthPath()); clientId: perfil (ex.: 'hub-global').
// INDETERMINADO cobre o erro de leitura (EPERM/ENOENT transitorio enquanto o Chrome ainda
// segura handles do perfil) — exatamente a janela em que os drenos operam.
function inspecionarSessaoPersistida(authPath, clientId) {
    const idbDir = path.join(
        authPath, `session-${clientId}`, 'Default', 'IndexedDB',
        'https_web.whatsapp.com_0.indexeddb.leveldb'
    );
    try {
        if (!fs.existsSync(idbDir)) { return ESTADO_AUSENTE; }
        const temDados = fs.readdirSync(idbDir).some(f => /^MANIFEST-|\.ldb$|\.log$|\.sst$/i.test(f));
        return temDados ? ESTADO_PRESENTE : ESTADO_AUSENTE;
    } catch (_) {
        return ESTADO_INDETERMINADO;
    }
}

// Para quem decide ABORTAR: na duvida nao bloqueia o fluxo, deixa o bootstrap decidir.
function sessaoPersistidaAusente(authPath, clientId) {
    return inspecionarSessaoPersistida(authPath, clientId) === ESTADO_AUSENTE;
}

// Para quem CONFIRMA a persistencia apos o dreno: na duvida segue drenando/avisa o
// operador, em vez de anunciar um sucesso que a proxima execucao vai desmentir.
function sessaoPersistidaConfirmada(authPath, clientId) {
    return inspecionarSessaoPersistida(authPath, clientId) === ESTADO_PRESENTE;
}

module.exports = {
    ESTADO_AUSENTE,
    ESTADO_PRESENTE,
    ESTADO_INDETERMINADO,
    inspecionarSessaoPersistida,
    sessaoPersistidaAusente,
    sessaoPersistidaConfirmada
};
