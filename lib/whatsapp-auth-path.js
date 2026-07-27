// Fonte unica do caminho da sessao autenticada do WhatsApp (LocalAuth).
// O diretorio NAO pode viver dentro da arvore do repositorio: ele contem as
// credenciais de sessao do WhatsApp Web, e qualquer zip/backup/sync da pasta
// do projeto carregaria a sessao junto.
// Override opcional: variavel de ambiente WHATSAPP_AUTH_PATH.
const path = require('path');

function resolveAuthPath() {
    const override = (process.env.WHATSAPP_AUTH_PATH || '').trim();
    if (override) return path.resolve(override);
    const base = process.env.LOCALAPPDATA || process.env.HOME || process.cwd();
    return path.join(base, 'Automacoes', 'wwebjs_auth');
}

module.exports = { resolveAuthPath };
