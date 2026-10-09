// {
//   "name": "aplicar-patches",
//   "description": "Aplicador de patches unificados sem dependencias (substitui o patch-package no postinstall de lib/)"
// }
'use strict';

// Substitui o patch-package no postinstall de lib/ (ver lib/package.json): a cadeia dele (braces@3.0.3,
// CVE-2026-93687) não tem correção publicada. Uso: node scripts/aplicar-patches.js [raiz] [patches];
// padrão: lib/ e lib/patches.
//
// Formato: diff unificado do git. Recusado com erro: rename, cópia, binário, modo, criação e remoção,
// "\ No newline at end of file", hunk sem contexto ou sem alteração, contagem do @@ que não bate com o
// corpo, início de @@ inconsistente, ---/+++ de caminhos diferentes e alvo repetido (sem diferenciar
// maiúsculas, porque o NTFS não diferencia).
//
// Casamento estrito, sem deslocamento: cada hunk é verificado só no seu cabeçalho. 'original': contexto e
// '-' casam em a; 'já aplicado': contexto e '+' casam em c. Se os dois casam, vale o estado dos outros
// hunks do arquivo ou, na falta deles, o bloco mais longo (empate é erro). Estado misto é erro.
//
// Garantias: se um patch falhar, nada é gravado. Cada alvo é gravado por temporário + rename (atômico por
// arquivo). Entre arquivos NÃO há atomicidade: falha no segundo deixa o primeiro gravado, e a reexecução
// completa o trabalho. O BOM do .patch sai antes da análise; o BOM do alvo fica fora do casamento e é
// preservado. O EOL do alvo precisa ser uniforme (CRLF ou LF). Caminhos ficam dentro da raiz, também
// depois de realpath.

const fs = require('fs');
const path = require('path');

const PADRAO_RAIZ = path.resolve(__dirname, '..');
const BOM = '﻿';
const RE_HUNK = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/;
// Metadados de diff fora do escopo suportado: cada um vira erro explícito.
const METADADOS_NAO_SUPORTADOS = [
    [/^rename (from|to) /, 'renomeação de arquivo'],
    [/^copy (from|to) /, 'cópia de arquivo'],
    [/^(dis)?similarity index /, 'renomeação ou reescrita de arquivo'],
    [/^(Binary files |GIT binary patch)/, 'arquivo binário'],
    [/^(old|new) mode /, 'mudança de modo'],
    [/^(new|deleted) file mode /, 'criação ou remoção de arquivo'],
];

class ErroPatch extends Error {
    constructor(mensagem) {
        super(mensagem);
        this.name = 'ErroPatch';
    }
}

const existeArquivo = (c) => fs.existsSync(c) && fs.statSync(c).isFile();
const existeDiretorio = (c) => fs.existsSync(c) && fs.statSync(c).isDirectory();
// Remove o prefixo a/ ou b/ que o git põe nos cabeçalhos.
const semPrefixo = (c) => (c.startsWith('a/') || c.startsWith('b/') ? c.slice(2) : c);
// O bloco casa exatamente a partir do índice p (0-based), e só ali.
const casaEm = (linhas, bloco, p) => p >= 0 && p + bloco.length <= linhas.length
    && bloco.every((t, k) => linhas[p + k] === t);

function motivoCaminhoRecusado(caminho) {
    if (caminho === '') return 'vazio';
    if (caminho.includes('\0')) return 'byte nulo';
    if (caminho.includes('\\')) return 'barra invertida não é aceita em patch';
    if (caminho.startsWith('/') || /^[A-Za-z]:/.test(caminho)) return 'caminho absoluto';
    if (caminho.split('/').some((s) => s === '' || s === '.' || s === '..')) return 'sai da raiz ou tem segmento vazio';
    return null;
}

// Validação léxica do caminho de um cabeçalho do patch. Não toca no disco.
function normalizarCaminhoPatch(bruto, nomePatch) {
    const caminho = semPrefixo(bruto);
    const motivo = motivoCaminhoRecusado(caminho);
    if (motivo) throw new ErroPatch(`${nomePatch}: caminho recusado "${bruto}" (${motivo})`);
    return caminho;
}

// Valida uma seção e monta, por hunk, os textos antigo (contexto e '-') e novo (contexto e '+').
function validarSecao(s, nomePatch) {
    const erro = (m) => new ErroPatch(`${nomePatch}: ${m}`);
    if (s.caminho === null) throw erro('cabeçalho --- sem +++ correspondente');
    if (s.hunks.length === 0) throw erro(`${s.caminho} sem hunks`);
    let deslocamento = 0; // soma de (novo - antigo) dos hunks anteriores: o c de cada hunk depende dela
    let proximaLinha = 1;
    const hunks = s.hunks.map((h) => {
        const onde = `hunk de ${s.caminho} (@@ linha ${h.a})`;
        if (!h.linhas.some((l) => l.tipo === ' ')) throw erro(`${onde} sem linhas de contexto; não é possível localizá-lo com segurança`);
        if (h.linhas.every((l) => l.tipo === ' ')) throw erro(`${onde} sem alteração`);
        if (h.c !== h.a + deslocamento) {
            throw erro(`hunk de ${s.caminho}: cabeçalho inconsistente (@@ -${h.a} +${h.c}, esperado +${h.a + deslocamento})`);
        }
        if (h.a < proximaLinha) throw erro(`${onde} fora de ordem ou sobreposto`);
        // O git copia o BOM do alvo para o contexto da linha 1: sai do casamento, como o BOM do alvo.
        const primeira = h.linhas.find((l) => l.tipo !== '+');
        if (h.a === 1 && primeira.texto.startsWith(BOM)) primeira.texto = primeira.texto.slice(BOM.length);
        const antigo = h.linhas.filter((l) => l.tipo !== '+').map((l) => l.texto);
        const novo = h.linhas.filter((l) => l.tipo !== '-').map((l) => l.texto);
        proximaLinha = h.a + antigo.length;
        deslocamento += novo.length - antigo.length;
        return { a: h.a, c: h.c, antigo, novo };
    });
    return { caminho: s.caminho, hunks };
}

// Converte o .patch em [{ caminho, hunks: [{ a, c, antigo, novo }] }]. Não toca no disco.
function analisarPatch(textoPatch, nomePatch = 'patch') {
    const texto = textoPatch.startsWith(BOM) ? textoPatch.slice(BOM.length) : textoPatch;
    const brutas = texto.split('\n');
    if (brutas[brutas.length - 1] === '') brutas.pop(); // quebra final não pode completar hunk truncado
    const erro = (m) => new ErroPatch(`${nomePatch}: ${m}`);
    const secoes = [];
    let secao = null;
    let hunk = null;
    let restoA = 0;
    let restoN = 0;

    for (const bruta of brutas) {
        const linha = bruta.endsWith('\r') ? bruta.slice(0, -1) : bruta;

        // Corpo do hunk: consome exatamente as linhas que o cabeçalho @@ anuncia.
        if (restoA > 0 || restoN > 0) {
            if (linha.startsWith('\\')) throw erro(`"\\ No newline at end of file" não suportado (${secao.caminho})`);
            if (linha.startsWith('@@ ') || linha.startsWith('diff --git ')) {
                throw erro(`hunk truncado em ${secao.caminho} (faltam linhas em relação ao cabeçalho @@)`);
            }
            const tipo = linha === '' ? ' ' : linha.charAt(0); // linha vazia é contexto vazio
            if (!' +-'.includes(tipo)) throw erro(`linha inesperada no hunk de ${secao.caminho}: "${linha}"`);
            if (tipo !== '+') restoA -= 1;
            if (tipo !== '-') restoN -= 1;
            if (restoA < 0 || restoN < 0) throw erro(`hunk de ${secao.caminho} tem linhas além da contagem do cabeçalho @@`);
            hunk.linhas.push({ tipo, texto: linha.slice(1) });
            continue;
        }

        if (linha === '') continue;
        if (linha.startsWith('\\')) throw erro('"\\ No newline at end of file" não suportado');
        if (linha.startsWith('diff --git ')) {
            hunk = null;
            secao = null;
            continue;
        }
        if (linha.startsWith('--- ') || linha.startsWith('+++ ')) {
            const deOrigem = linha.startsWith('--- ');
            const bruto = linha.slice(4).split('\t')[0];
            hunk = null;
            if (bruto === '/dev/null') throw erro(deOrigem ? 'criação de arquivo não suportada' : 'remoção de arquivo não suportada');
            if (deOrigem) {
                if (secao && secao.caminho === null) throw erro('cabeçalho --- sem +++ correspondente');
                secao = { origem: semPrefixo(bruto), caminho: null, hunks: [] };
                secoes.push(secao);
            } else {
                if (!secao || secao.caminho !== null) throw erro('cabeçalho +++ sem --- correspondente');
                if (semPrefixo(bruto) !== secao.origem) {
                    throw erro(`cabeçalhos --- e +++ apontam para arquivos diferentes (renomeação não suportada): "${secao.origem}" e "${semPrefixo(bruto)}"`);
                }
                secao.caminho = normalizarCaminhoPatch(bruto, nomePatch);
            }
            continue;
        }
        const cabecalho = RE_HUNK.exec(linha);
        if (cabecalho) {
            if (!secao || secao.caminho === null) throw erro('hunk @@ sem cabeçalho +++ do arquivo');
            hunk = { a: Number(cabecalho[1]), c: Number(cabecalho[3]), linhas: [] };
            restoA = cabecalho[2] === undefined ? 1 : Number(cabecalho[2]);
            restoN = cabecalho[4] === undefined ? 1 : Number(cabecalho[4]);
            secao.hunks.push(hunk);
            continue;
        }
        const naoSuportado = METADADOS_NAO_SUPORTADOS.find(([re]) => re.test(linha));
        if (naoSuportado) throw erro(`formato não suportado (${naoSuportado[1]}): "${linha}"`);
        // Linha de diff depois que a contagem fechou não some em silêncio; "-- " (format-patch) é exceção.
        if (hunk && ['+', '-', ' '].includes(linha.charAt(0)) && linha !== '-- ') {
            throw erro(`hunk de ${secao.caminho} tem linhas além da contagem do cabeçalho @@: "${linha}"`);
        }
    }

    if (restoA > 0 || restoN > 0) throw erro(`hunk truncado em ${secao.caminho} (faltam linhas em relação ao cabeçalho @@)`);
    if (secoes.length === 0) throw erro('nenhum arquivo encontrado (sem cabeçalhos ---/+++)');
    return secoes.map((s) => validarSecao(s, nomePatch));
}

// Separa o alvo em linhas: BOM à parte, EOL uniforme (CRLF ou LF) e presença de quebra final.
function dividirArquivo(texto, rotulo) {
    const bom = texto.startsWith(BOM) ? BOM : '';
    const partes = texto.slice(bom.length).split('\n');
    const comQuebraFinal = partes[partes.length - 1] === '';
    if (comQuebraFinal) partes.pop();
    const terminadas = comQuebraFinal ? partes.length : partes.length - 1;
    const crlf = partes.slice(0, terminadas).filter((p) => p.endsWith('\r')).length;
    if (crlf > 0 && crlf < terminadas) {
        throw new ErroPatch(`${rotulo}: EOL misto (CRLF e LF no mesmo arquivo); o aplicador não altera esse arquivo`);
    }
    return {
        bom,
        eol: crlf > 0 ? '\r\n' : '\n',
        comQuebraFinal,
        linhas: partes.map((p, i) => (i < terminadas && p.endsWith('\r') ? p.slice(0, -1) : p)),
    };
}

// Estado do arquivo ('original' ou 'aplicado') a partir dos hunks; o critério está no cabeçalho.
function decidirEstado(linhas, hunks, rotulo) {
    const porHunk = hunks.map((h) => {
        const original = casaEm(linhas, h.antigo, h.a - 1);
        const aplicado = casaEm(linhas, h.novo, h.c - 1);
        if (!original && !aplicado) {
            throw new ErroPatch(`${rotulo}: hunk @@ -${h.a} não casa com o conteúdo atual (contexto divergente ou ausente)`);
        }
        return original && aplicado ? 'ambos' : original ? 'original' : 'aplicado';
    });
    const definidos = [...new Set(porHunk.filter((e) => e !== 'ambos'))];
    if (definidos.length > 1) throw new ErroPatch(`${rotulo}: estado misto (alguns hunks já aplicados e outros não); o arquivo não foi alterado`);
    const estados = hunks.map((h, i) => {
        if (porHunk[i] !== 'ambos') return porHunk[i];
        if (definidos.length === 1) return definidos[0];
        if (h.novo.length === h.antigo.length) {
            throw new ErroPatch(`${rotulo}: hunk @@ -${h.a} em estado ambíguo (os dois blocos casam e têm o mesmo tamanho); o arquivo não foi alterado`);
        }
        return h.novo.length > h.antigo.length ? 'aplicado' : 'original';
    });
    if (new Set(estados).size > 1) throw new ErroPatch(`${rotulo}: estado misto entre hunks ambíguos; o arquivo não foi alterado`);
    return estados[0];
}

// Aplica os hunks sobre o texto do alvo, em memória. Retorna { conteudo, alterou }.
function aplicarHunks(texto, hunks, rotulo) {
    const arq = dividirArquivo(texto, rotulo);
    if (decidirEstado(arq.linhas, hunks, rotulo) === 'aplicado') return { conteudo: texto, alterou: false };
    let saida = [];
    let pos = 0;
    for (const h of hunks) {
        saida = saida.concat(arq.linhas.slice(pos, h.a - 1), h.novo);
        pos = h.a - 1 + h.antigo.length;
    }
    saida = saida.concat(arq.linhas.slice(pos));
    const corpo = saida.length === 0 ? '' : saida.join(arq.eol) + (arq.comQuebraFinal ? arq.eol : '');
    return { conteudo: arq.bom + corpo, alterou: true };
}

// Verdadeiro quando caminhoReal fica dentro de raizReal (ambos absolutos ou já resolvidos por realpath).
function estaDentro(raizReal, caminhoReal) {
    const rel = path.relative(raizReal, caminhoReal);
    return rel === '' || !(rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel));
}

function resolverAlvo(raizAbs, caminho) {
    const alvo = path.resolve(raizAbs, ...caminho.split('/'));
    if (alvo === raizAbs || !estaDentro(raizAbs, alvo)) throw new ErroPatch(`caminho fora da raiz: ${caminho}`);
    return alvo;
}

// Alvo existente e, depois de resolver links, dentro da raiz. Pacote em node_modules precisa estar instalado
// (o postinstall roda depois do npm install).
function verificarAlvo(raizAbs, raizReal, caminho, nomePatch) {
    const partes = caminho.split('/');
    if (partes[0] === 'node_modules' && partes.length >= 3) {
        const pacote = partes[1].startsWith('@') ? partes.slice(1, 3) : partes.slice(1, 2);
        if (partes.length >= pacote.length + 2 && !existeDiretorio(path.join(raizAbs, 'node_modules', ...pacote))) {
            throw new ErroPatch(`${nomePatch}: pacote alvo "${pacote.join('/')}" ausente em node_modules; instale as dependências antes`);
        }
    }
    const alvo = resolverAlvo(raizAbs, caminho);
    if (!existeArquivo(alvo)) throw new ErroPatch(`${nomePatch}: arquivo alvo ausente: ${caminho}`);
    if (!estaDentro(raizReal, fs.realpathSync(alvo)) || !estaDentro(raizReal, fs.realpathSync(path.dirname(alvo)))) {
        throw new ErroPatch(`${nomePatch}: alvo resolve para fora da raiz via link simbólico: ${caminho}`);
    }
    return alvo;
}

// UTF-8 estrito: byte inválido é erro. ignoreBOM: true mantém o BOM como U+FEFF (regravação com os mesmos bytes).
function decodificarUtf8(bytes, mensagem) {
    try {
        return new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
    } catch {
        throw new ErroPatch(mensagem);
    }
}

// Temporário no mesmo diretório e rename por cima: atômico por arquivo, não entre arquivos.
function gravarAtomico(alvo, conteudo) {
    const temp = path.join(path.dirname(alvo), `.${path.basename(alvo)}.${process.pid}.tmp`);
    try {
        fs.writeFileSync(temp, conteudo, { encoding: 'utf8', flag: 'wx' });
        fs.renameSync(temp, alvo);
    } catch (erro) {
        fs.rmSync(temp, { force: true });
        throw new ErroPatch(`não foi possível gravar ${alvo}: ${erro.message}`);
    }
}

function listarPatches(dirPatches) {
    if (!existeDiretorio(dirPatches)) return [];
    return fs.readdirSync(dirPatches).filter((n) => n.endsWith('.patch') && existeArquivo(path.join(dirPatches, n))).sort();
}

// Aplica todos os *.patch de diretorioPatches sobre raiz. Calcula tudo antes e só então grava.
// Retorna [{ patch, caminho, status }], com status 'aplicado' ou 'ja-aplicado'.
function aplicarPatches({ raiz = PADRAO_RAIZ, diretorioPatches } = {}) {
    const raizAbs = path.resolve(raiz);
    const dirPatches = path.resolve(diretorioPatches || path.join(raizAbs, 'patches'));
    if (!existeDiretorio(raizAbs)) throw new ErroPatch(`diretório raiz inexistente: ${raizAbs}`);
    const raizReal = fs.realpathSync(raizAbs);

    const vistos = new Map(); // alvo em minúsculas -> patch que o referencia (NTFS não diferencia caixa)
    const planos = [];
    for (const nomePatch of listarPatches(dirPatches)) {
        const bytes = fs.readFileSync(path.join(dirPatches, nomePatch));
        const texto = decodificarUtf8(bytes, `${nomePatch}: arquivo de patch não é UTF-8 válido`);
        for (const { caminho, hunks } of analisarPatch(texto, nomePatch)) {
            const chave = caminho.toLowerCase();
            if (vistos.has(chave)) {
                throw new ErroPatch(`${nomePatch}: alvo repetido "${caminho}" (também em ${vistos.get(chave)}); a comparação ignora maiúsculas`);
            }
            vistos.set(chave, nomePatch);
            const alvo = verificarAlvo(raizAbs, raizReal, caminho, nomePatch);
            const rotulo = `${nomePatch} -> ${caminho}`;
            const original = decodificarUtf8(fs.readFileSync(alvo), `${rotulo}: arquivo alvo não é UTF-8 válido; o aplicador só altera arquivos UTF-8`);
            const { conteudo, alterou } = aplicarHunks(original, hunks, rotulo);
            planos.push({ nomePatch, caminho, alvo, conteudo, alterou });
        }
    }
    for (const plano of planos.filter((p) => p.alterou)) gravarAtomico(plano.alvo, plano.conteudo);
    return planos.map((p) => ({ patch: p.nomePatch, caminho: p.caminho, status: p.alterou ? 'aplicado' : 'ja-aplicado' }));
}

function main(argumentos = process.argv.slice(2)) {
    const [raiz, diretorioPatches] = argumentos;
    try {
        const resultados = aplicarPatches({ raiz, diretorioPatches });
        if (resultados.length === 0) console.log('aplicar-patches: nenhum arquivo .patch para aplicar.');
        for (const r of resultados) {
            console.log(`${r.status === 'aplicado' ? 'aplicado' : 'já aplicado'}: ${r.caminho} (${r.patch})`);
        }
        return 0;
    } catch (erro) {
        if (erro instanceof ErroPatch) console.error(`aplicar-patches: ${erro.message}`);
        else console.error('aplicar-patches: erro inesperado:', erro);
        return 1;
    }
}

module.exports = {
    aplicarPatches,
    analisarPatch,
    aplicarHunks,
    normalizarCaminhoPatch,
    resolverAlvo,
    listarPatches,
    ErroPatch,
    PADRAO_RAIZ,
};

if (require.main === module) {
    process.exitCode = main();
}
