// {
//   "name": "log-masking",
//   "description": "Mascaramento de dados sensiveis em log (paridade com Protect-SensitiveData / lib/python/log_masking.py)"
// }
'use strict';

// Fonte da paridade: lib/Lib-Logging.psm1 -> Protect-SensitiveData.
// As tres implementacoes (PS, Python, Node) sao mantidas alinhadas por teste.
const EMAIL_RE = /([a-zA-Z0-9._%+-])[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/g;
const SECRET_RE = /(token|key|password|pass|secret|credential|auth|apikey|client_secret)([:= ]\s*)([a-zA-Z0-9._%+-]{4,})/gi;
const ORACLE_HOST_RE = /(DESCRIPTION\s*=\s*\(ADDRESS\s*=\s*\(PROTOCOL\s*=\s*TCP\)\(HOST\s*=\s*)[^)]+/g;

function maskSensitive(text) {
    if (text === undefined || text === null) return '';
    const s = String(text);
    if (!s.trim()) return '';
    return s
        .replace(EMAIL_RE, '$1***@$2')
        .replace(SECRET_RE, '$1$2[REDACTED]')
        .replace(ORACLE_HOST_RE, '$1[HIDDEN]');
}

module.exports = { maskSensitive };
