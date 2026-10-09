// Fork vendorizado do extract-zip 2.0.1 (BSD-2-Clause, ver LICENSE), com correções de segurança para
// CVE-2026-19693 e CVE-2026-56876: entradas de symlink e nomes de arquivo que escreviam fora do destino.
// Sem versão corrigida publicada e pacote abandonado desde 2021. Escopo e motivo: ver README.md desta pasta.
const debug = require('debug')('extract-zip')
// eslint-disable-next-line node/no-unsupported-features/node-builtins
const { createWriteStream, promises: fs } = require('fs')
const getStream = require('get-stream')
const path = require('path')
const { promisify } = require('util')
const stream = require('stream')
const yauzl = require('yauzl')

const openZip = promisify(yauzl.open)
const pipeline = promisify(stream.pipeline)

// Limite de saltos de symlink por resolução de alvo, contado no total entre todos os ramos (mesma regra do
// MAXSYMLINKS do kernel Linux). Limitar só a profundidade deixava o trabalho exponencial: um componente repetido
// é resolvido de novo a cada nível.
const MAX_SALTOS_SYMLINK = 40

// Verdadeiro quando `alvo` é `raiz` ou está dentro dela. Compara pelo path.relative, que usa separador:
// "/dest-evil" NÃO está dentro de "/dest", ao contrário de um startsWith cru.
function estaDentro (raiz, alvo) {
  const relativo = path.relative(raiz, alvo)
  if (relativo === '') return true
  return relativo !== '..' && !relativo.startsWith('..' + path.sep) && !path.isAbsolute(relativo)
}

// lstat que devolve null quando o caminho não existe (ENOENT) ou um componente do pai não é diretório (ENOTDIR).
async function lstatOuNulo (caminho) {
  try {
    return await fs.lstat(caminho)
  } catch (err) {
    if (err.code === 'ENOENT' || err.code === 'ENOTDIR') return null
    throw err
  }
}

// Resolve com realpath o ancestral existente mais próximo de `caminho` (o próprio, se existir). Componente ausente
// não pode ser seguido, então sobe até o primeiro que existe. lstat enxerga links; um link pendente faz o realpath falhar.
async function ancestralExistenteReal (caminho) {
  let atual = caminho
  while ((await lstatOuNulo(atual)) === null && path.dirname(atual) !== atual) {
    atual = path.dirname(atual)
  }
  return fs.realpath(atual)
}

// Absoluto ou com unidade ("C:foo" é relativo à unidade no Windows, não ao diretório do link).
function ehAlvoAbsoluto (alvo) {
  return path.isAbsolute(alvo) || /^[a-zA-Z]:/.test(alvo)
}

// Resolve o alvo de um symlink do zip como o SO resolveria, a partir de `baseReal` (diretório real onde o link
// será criado). Lança erro quando o resultado pode sair de `raiz`. Regras, em caso de dúvida rejeita:
//  - alvo absoluto é rejeitado, tanto o do zip quanto o de link que já existia no destino;
//  - componente que já é symlink é seguido (cadeias legítimas, como Versions/Current em bundles macOS, passam),
//    e cada salto conta em `orcamento.saltos`, compartilhado por toda a resolução;
//  - ".." logo após componente inexistente é rejeitado: o SO ainda não sabe aonde ele leva, e outra entrada
//    do zip poderia criar esse componente como symlink depois.
// Retorna o caminho resolvido (absoluto) quando o alvo fica dentro de `raiz`.
async function resolverAlvoSymlink (raiz, baseReal, nome, alvo, orcamento = { saltos: 0 }) {
  if (ehAlvoAbsoluto(alvo)) {
    throw new Error(`Symlink "${nome}" tem alvo absoluto "${alvo}" (rejeitado)`)
  }

  let atual = baseReal
  let existe = true
  for (const parte of alvo.split(/[\\/]+/)) {
    if (parte === '' || parte === '.') continue

    if (parte === '..') {
      if (!existe) {
        throw new Error(`Symlink "${nome}" tem alvo "${alvo}" com ".." após componente inexistente (rejeitado: não verificável)`)
      }
      atual = path.dirname(atual)
      continue
    }

    const candidato = path.join(atual, parte)
    const stat = existe ? await lstatOuNulo(candidato) : null

    if (stat !== null && stat.isSymbolicLink()) {
      orcamento.saltos += 1
      if (orcamento.saltos > MAX_SALTOS_SYMLINK) {
        throw new Error(`Symlink "${nome}" tem cadeia de links longa demais (rejeitado)`)
      }
      // Segue o link: o alvo dele é resolvido a partir do diretório atual, como o SO faria.
      const destinoDoLink = await fs.readlink(candidato)
      if (ehAlvoAbsoluto(destinoDoLink)) {
        // O alvo veio do disco, não do zip. O fork não resolve caminho absoluto, mesmo dentro do destino.
        throw new Error(`Symlink "${nome}" passa pelo link pré-existente "${path.relative(raiz, candidato)}" com alvo absoluto "${destinoDoLink}" (rejeitado: o fork não resolve alvo absoluto de link que já existia no destino)`)
      }
      atual = await resolverAlvoSymlink(raiz, atual, nome, destinoDoLink, orcamento)
      const resultado = await lstatOuNulo(atual)
      existe = resultado !== null && resultado.isDirectory()
      continue
    }

    atual = candidato
    existe = stat !== null && stat.isDirectory()
  }

  if (!estaDentro(raiz, atual)) {
    throw new Error(`Symlink "${nome}" aponta para fora do diretório de extração: "${alvo}" (rejeitado)`)
  }
  return atual
}

// Rejeita gravar sobre um destino que já é symlink: mkdir e createWriteStream seguiriam o link para fora.
// Cobre o ataque de duas entradas com o mesmo nome (symlink seguido de arquivo regular).
// path.resolve tira a barra final: em POSIX, lstat("x/") segue o link "x", e a entrada de diretório "x/" passaria.
async function garantirDestinoNaoSymlink (dest, nome) {
  const stat = await lstatOuNulo(path.resolve(dest))
  if (stat !== null && stat.isSymbolicLink()) {
    throw new Error(`Destino "${nome}" já existe como symlink; gravar sobre ele poderia escrever fora do diretório (rejeitado)`)
  }
}

class Extractor {
  constructor (zipPath, opts) {
    this.zipPath = zipPath
    this.opts = opts
  }

  async extract () {
    debug('opening', this.zipPath, 'with opts', this.opts)

    this.zipfile = await openZip(this.zipPath, { lazyEntries: true })
    this.canceled = false

    return new Promise((resolve, reject) => {
      this.zipfile.on('error', err => {
        this.canceled = true
        reject(err)
      })
      this.zipfile.readEntry()

      this.zipfile.on('close', () => {
        if (!this.canceled) {
          debug('zip extraction complete')
          resolve()
        }
      })

      this.zipfile.on('entry', async entry => {
        /* istanbul ignore if */
        if (this.canceled) {
          debug('skipping entry', entry.fileName, { cancelled: this.canceled })
          return
        }

        debug('zipfile entry', entry.fileName)

        if (entry.fileName.startsWith('__MACOSX/')) {
          this.zipfile.readEntry()
          return
        }

        const destino = path.join(this.opts.dir, entry.fileName)
        const destDir = path.dirname(destino)

        try {
          // Nome que sai do destino (ex.: "../x") é rejeitado antes de qualquer mkdir.
          if (!estaDentro(this.opts.dir, destino)) {
            throw new Error(`Entrada "${entry.fileName}" resolve para fora do diretório de extração (rejeitada)`)
          }

          // Antes de qualquer mkdir: o ancestral existente mais próximo precisa ser real e ficar dentro do destino.
          // Um mkdir recursivo seguiria junção ou symlink pré-existente para fora e criaria diretórios lá.
          const ancestralReal = await ancestralExistenteReal(destDir)
          if (!estaDentro(this.opts.dir, ancestralReal)) {
            throw new Error(`Out of bound path "${ancestralReal}" found while processing file ${entry.fileName}`)
          }

          await fs.mkdir(destDir, { recursive: true })

          const canonicalDestDir = await fs.realpath(destDir)
          // Contenção por separador (ver estaDentro), no diretório pai e também no caminho final.
          const destinoFinal = path.join(canonicalDestDir, path.basename(destino))
          if (!estaDentro(this.opts.dir, canonicalDestDir) || !estaDentro(this.opts.dir, destinoFinal)) {
            throw new Error(`Out of bound path "${canonicalDestDir}" found while processing file ${entry.fileName}`)
          }

          await this.extractEntry(entry)
          debug('finished processing', entry.fileName)
          this.zipfile.readEntry()
        } catch (err) {
          this.canceled = true
          this.zipfile.close()
          reject(err)
        }
      })
    })
  }

  async extractEntry (entry) {
    /* istanbul ignore if */
    if (this.canceled) {
      debug('skipping entry extraction', entry.fileName, { cancelled: this.canceled })
      return
    }

    if (this.opts.onEntry) {
      this.opts.onEntry(entry, this.zipfile)
    }

    const dest = path.join(this.opts.dir, entry.fileName)

    // convert external file attr int into a fs stat mode int
    const mode = (entry.externalFileAttributes >> 16) & 0xFFFF
    // check if it's a symlink or dir (using stat mode constants)
    const IFMT = 61440
    const IFDIR = 16384
    const IFLNK = 40960
    const symlink = (mode & IFMT) === IFLNK
    let isDir = (mode & IFMT) === IFDIR

    // Failsafe, borrowed from jsZip
    if (!isDir && entry.fileName.endsWith('/')) {
      isDir = true
    }

    // check for windows weird way of specifying a directory
    // https://github.com/maxogden/extract-zip/issues/13#issuecomment-154494566
    const madeBy = entry.versionMadeBy >> 8
    if (!isDir) isDir = (madeBy === 0 && entry.externalFileAttributes === 16)

    debug('extracting entry', { filename: entry.fileName, isDir: isDir, isSymlink: symlink })

    const procMode = this.getExtractedMode(mode, isDir) & 0o777

    // always ensure folders are created
    const destDir = isDir ? dest : path.dirname(dest)

    // Antes de qualquer escrita, o destino final não pode ser symlink (ver garantirDestinoNaoSymlink).
    await garantirDestinoNaoSymlink(dest, entry.fileName)

    const mkdirOptions = { recursive: true }
    if (isDir) {
      mkdirOptions.mode = procMode
    }
    debug('mkdir', { dir: destDir, ...mkdirOptions })
    await fs.mkdir(destDir, mkdirOptions)
    if (isDir) return

    debug('opening read stream', dest)
    const readStream = await promisify(this.zipfile.openReadStream.bind(this.zipfile))(entry)

    if (symlink) {
      const link = await getStream(readStream)
      // O alvo é validado antes de criar o link. O diretório pai já foi verificado como real e dentro do destino.
      await resolverAlvoSymlink(this.opts.dir, await fs.realpath(path.dirname(dest)), entry.fileName, link)
      debug('creating symlink', link, dest)
      await fs.symlink(link, dest)
    } else {
      await pipeline(readStream, createWriteStream(dest, { mode: procMode }))
    }
  }

  getExtractedMode (entryMode, isDir) {
    let mode = entryMode
    // Set defaults, if necessary
    if (mode === 0) {
      if (isDir) {
        if (this.opts.defaultDirMode) {
          mode = parseInt(this.opts.defaultDirMode, 10)
        }

        if (!mode) {
          mode = 0o755
        }
      } else {
        if (this.opts.defaultFileMode) {
          mode = parseInt(this.opts.defaultFileMode, 10)
        }

        if (!mode) {
          mode = 0o644
        }
      }
    }

    return mode
  }
}

module.exports = async function (zipPath, opts) {
  debug('creating target directory', opts.dir)

  if (!path.isAbsolute(opts.dir)) {
    throw new Error('Target directory is expected to be absolute')
  }

  await fs.mkdir(opts.dir, { recursive: true })
  opts.dir = await fs.realpath(opts.dir)
  return new Extractor(zipPath, opts).extract()
}
