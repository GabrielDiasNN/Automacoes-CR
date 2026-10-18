export const meta = {
  name: 'auditoria-acervo-queries',
  description: 'Audita o acervo Oracle de 212 consultas com inventario, quatro eixos, refutacao em duas rodadas por achado e por edicao. Nao altera SQL de producao nem remove arquivos.',
  whenToUse: 'Auditoria periodica do acervo de consultas SQL do ERP SGT, incluindo o SQL de runtime das automacoes',
  phases: [
    { title: 'Inventario', detail: 'uma linha por consulta, em lotes deterministicos' },
    { title: 'Auditar', detail: 'semantica, desempenho, governanca e consistencia em paralelo' },
    { title: 'Refutar', detail: 'duas rodadas adversariais por achado unico' },
    { title: 'Editar', detail: 'propositor so para achados mantidos com classe FATO; refutador de cada patch' },
    { title: 'Gates', detail: 'git apply --check, encoding e Test-SqlPerformance em copia de scratch' },
    { title: 'Julgar', detail: 'regra fixa define o destino de cada item' },
    { title: 'Escrever', detail: 'artefatos em docs/auditorias/queries/<data>/' },
  ],
}

const SCHEMA_INVENTARIO = {
  type: 'object',
  properties: {
    linhas: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          arquivo: { type: 'string' },
          pasta: { type: 'string' },
          tabelas: { type: 'array', items: { type: 'string' } },
          joins: { type: 'array', items: { type: 'string' } },
          filtros: { type: 'array', items: { type: 'string' } },
          binds: { type: 'array', items: { type: 'string' } },
          colunas_saida: { type: 'array', items: { type: 'string' } },
          sonda_literal_fixo: { type: 'boolean' },
          tem_order_by: { type: 'boolean' },
          observacao: { type: 'string' },
        },
        required: ['arquivo', 'pasta', 'tabelas', 'colunas_saida', 'sonda_literal_fixo', 'tem_order_by', 'observacao'],
      },
    },
  },
  required: ['linhas'],
}

const SCHEMA_AUDITORIA = {
  type: 'object',
  properties: {
    achados: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          arquivo: { type: 'string' },
          linha: { type: 'number' },
          trecho: { type: 'string' },
          titulo: { type: 'string' },
          severidade: { type: 'string', enum: ['critica', 'alta', 'media', 'baixa'] },
          classe: { type: 'string', enum: ['FATO', 'VERIFICAR_ORACLE', 'DECISAO_AREA'] },
          evidencia: { type: 'string' },
          regra_citada: { type: 'string' },
        },
        required: ['arquivo', 'linha', 'trecho', 'titulo', 'severidade', 'classe', 'evidencia'],
      },
    },
  },
  required: ['achados'],
}

const SCHEMA_REFUTACAO = {
  type: 'object',
  properties: {
    veredito: { type: 'string', enum: ['REFUTADO', 'PARCIAL', 'MANTIDO'] },
    prova: { type: 'string' },
    linha_ou_regra: { type: 'string' },
    duvida: { type: 'string' },
  },
  required: ['veredito', 'prova'],
}

const SCHEMA_EDICAO = {
  type: 'object',
  properties: {
    nao_aplicavel: { type: 'boolean' },
    motivo: { type: 'string' },
    muda_colunas_saida: { type: 'boolean' },
    patch: { type: 'string' },
  },
  required: ['nao_aplicavel', 'motivo', 'patch'],
}

const SCHEMA_REFUTA_EDICAO = {
  type: 'object',
  properties: {
    veredito: { type: 'string', enum: ['APROVADA', 'REPROVADA'] },
    prova: { type: 'string' },
    quebra_contrato: { type: 'boolean' },
    regressao_desempenho: { type: 'boolean' },
  },
  required: ['veredito', 'prova'],
}

const SCHEMA_GATE = {
  type: 'object',
  properties: {
    patch_aplica: { type: 'boolean' },
    encoding_ok: { type: 'boolean' },
    perf_ok: { type: 'boolean' },
    saida_resumida: { type: 'string' },
  },
  required: ['patch_aplica', 'encoding_ok', 'perf_ok', 'saida_resumida'],
}

const SCHEMA_ESCRITA = {
  type: 'object',
  properties: {
    arquivos_escritos: { type: 'number' },
    observacao: { type: 'string' },
  },
  required: ['arquivos_escritos'],
}

// ---------------------------------------------------------------- configuracao
const cfg = args || {}
if (!cfg.scratch) {
  throw new Error('args.scratch e obrigatorio: pasta de trabalho para as copias dos gates')
}
// Data obrigatoria (DD-MM-YYYY): um padrao fixo gravaria a auditoria de hoje na pasta
// de outra data. O workflow nao pode ler o relogio (execucao deterministica).
if (!cfg.data || !/^\d{2}-\d{2}-\d{4}$/.test(cfg.data)) {
  throw new Error('args.data e obrigatorio no formato DD-MM-YYYY (pasta de saida da auditoria)')
}
const DATA = cfg.data
// Raiz do repositorio vinda dos args, nao fixa no codigo.
if (!cfg.repo) {
  throw new Error('args.repo e obrigatorio: caminho da raiz do repositorio')
}
const REPO = cfg.repo
const SAIDA = 'docs/auditorias/queries/' + DATA
const SCRATCH = cfg.scratch
const TAM_LOTE = 16
const MAX_ACHADOS = cfg.maxAchados || 150
const TETO_AGENTES = 900

const acervo = (cfg.acervo || []).map((a) => ({ arquivo: a, escopo: 'acervo' }))
const runtime = (cfg.runtime || []).map((a) => ({ arquivo: a, escopo: 'runtime' }))
const producao = (cfg.producao || []).map((a) => ({ arquivo: a, escopo: 'producao' }))
// Chave normalizada: o caminho devolvido pelo modelo pode vir com barra invertida,
// prefixo ./ ou da raiz, ou acento em outra forma Unicode. Sem isto um achado de
// producao cairia como 'acervo' e perderia a regra de severidade e o veto a patch.
function chaveArquivo(caminho) {
  let c = String(caminho || '').normalize('NFC').replace(/\\/g, '/').trim()
  const raiz = String(REPO).normalize('NFC').replace(/\\/g, '/').replace(/\/+$/, '') + '/'
  if (c.toLowerCase().startsWith(raiz.toLowerCase())) c = c.slice(raiz.length)
  return c.replace(/^\.\//, '').toLowerCase()
}
const ESCOPO = new Map()
for (const a of [...acervo, ...runtime, ...producao]) ESCOPO.set(chaveArquivo(a.arquivo), a.escopo)

const EIXOS = [
  {
    key: 'semantica',
    nome: 'correcao semantica',
    foco: 'Joins (fan-out, chave errada), NULLs em comparacoes e agregacoes, epoca de datas (serial, fuso, fim de mes), status (codigos e significado), tipos de coluna (texto "0" versus numero 0, comparacao implicita).',
  },
  {
    key: 'desempenho',
    nome: 'desempenho',
    foco: 'Subconsultas escalares executadas por linha, funcoes PL/SQL chamadas por linha, ausencia de ORDER BY com ROWNUM ou FETCH FIRST (resultado nao determinista), joins sem predicado, funcoes sobre colunas indexadas nos filtros.',
  },
  {
    key: 'governanca',
    nome: 'governanca',
    foco: 'Cabecalho com OBJETIVO e TIPO, rastreabilidade do arquivo de origem, encoding UTF-8 sem BOM, literais fixos sem explicacao, binds declarados, conformidade com docs/governanca/governance-contracts.md e CLAUDE.md.',
  },
  {
    key: 'consistencia',
    nome: 'consistencia entre automacoes',
    foco: 'A mesma regra de negocio implementada de formas diferentes em arquivos distintos (exemplo: extracao de NUMERO_MAQUINA, calculo de status, filtro de periodo). Compare com os outros arquivos do inventario.',
  },
]

const CONTEXTO = [
  'Repositorio: ' + REPO + ' (Windows, PowerShell 5.1 em producao, venv em .venv).',
  'Leitura obrigatoria antes de qualquer conclusao:',
  '- docs/oracle-schema/consultas/README.md (dono, promocao, fluxo de validacao);',
  '- docs/oracle-schema/consultas/REGRAS_NEGOCIO.md: secao 4 "Em aberto" e secao 5.11 "Decisoes de negocio em aberto" sao decisoes da area. So reabra um desses itens com evidencia NOVA, citando a linha da regra que contradiz;',
  '- docs/oracle-schema/consultas/PROPOSTA_CONSOLIDACAO.md: nenhuma duplicata e confirmada sem conferencia;',
  '- docs/oracle-schema/consultas/CATALOGO_QUERIES.md e validacao_status.json: "validada" significa parse e smoke de 1 linha, NAO equivalencia de regra;',
  '- CLAUDE.md (secao Catalogo Oracle) e CHANGELOG.md (Auditoria 1.3.102 e anteriores): nao reporte como novo o que ja foi corrigido ali.',
  'Regras absolutas: somente leitura; nao conecte ao Oracle; nao leia nem imprima o arquivo .env; nao edite nem remova arquivos.',
  'Classes: FATO (provado so pelo texto do codigo); VERIFICAR_ORACLE (depende de dado ou de plano de execucao); DECISAO_AREA (ja esta em REGRAS_NEGOCIO ou depende de regra de negocio).',
  'Evidencia: cite arquivo, linha real e o trecho exato lido por voce. Achado sem trecho verificavel nao deve ser reportado. Nao reporte estilo nem preferencia pessoal.',
].join('\n')

// ---------------------------------------------------------------- utilidades
function lotes(lista, n) {
  const out = []
  for (let i = 0; i < lista.length; i += n) out.push(lista.slice(i, i + n))
  return out
}

function cmp(a, b) {
  return a < b ? -1 : a > b ? 1 : 0
}

function cel(x) {
  return String(x === undefined || x === null ? '' : x).replace(/\|/g, '\\|').replace(/\r?\n/g, ' ')
}

const LOTES = [...lotes(acervo, TAM_LOTE), ...lotes(runtime, TAM_LOTE), ...lotes(producao, TAM_LOTE)]
const planejado = LOTES.length * (1 + EIXOS.length) + 5 * MAX_ACHADOS + 3
if (planejado > TETO_AGENTES) {
  throw new Error('plano com ate ' + planejado + ' agentes excede o teto de ' + TETO_AGENTES + '; reduza maxAchados')
}
log('plano: ' + LOTES.length + ' lotes, ' + EIXOS.length + ' eixos, ate ' + planejado + ' agentes')

// ---------------------------------------------------------------- prompts
function promptInventario(lote) {
  return [
    CONTEXTO,
    '',
    'Tarefa: INVENTARIO. Para cada arquivo abaixo, leia o SQL inteiro e devolva UMA linha: arquivo (caminho exato da lista), pasta, tabelas (schema.tabela), joins (condicao resumida), filtros, binds (:nome), colunas_saida (nomes na ordem do SELECT final), sonda_literal_fixo (true se ha literal fixo que define um caso de teste), tem_order_by, observacao curta.',
    'Nao invente colunas: copie os nomes do texto.',
    'Arquivos:',
    ...lote.map((a) => '- ' + a.arquivo + ' [' + a.escopo + ']'),
  ].join('\n')
}

function promptAuditoria(eixo, lote, inventarioDoLote) {
  return [
    CONTEXTO,
    '',
    'Papel: AUDITOR. Eixo: ' + eixo.nome + '. Foco: ' + eixo.foco,
    'Para cada achado devolva: arquivo; linha (numero real, contado no arquivo); trecho (texto exato da linha); titulo curto; severidade (critica, alta, media ou baixa); classe (FATO, VERIFICAR_ORACLE ou DECISAO_AREA); evidencia (por que e problema, citando o texto); regra_citada (linha de REGRAS_NEGOCIO.md que se aplica, ou string vazia).',
    'Se o tema estiver em REGRAS_NEGOCIO secao 4 "Em aberto" ou 5.11, a classe e DECISAO_AREA e nao reabra o tema sem evidencia nova.',
    'Arquivos de escopo producao: qualquer achado tem severidade critica.',
    'Inventario deste lote (referencia): ' + JSON.stringify(inventarioDoLote),
    'Arquivos do lote:',
    ...lote.map((a) => '- ' + a.arquivo + ' [' + a.escopo + ']'),
  ].join('\n')
}

function promptRefutador1(f) {
  return [
    CONTEXTO,
    '',
    'Papel: REFUTADOR ADVERSARIAL (rodada 1). Voce nao viu nenhum outro achado. Tarefa: provar que o achado abaixo e FALSO: coberto por guarda no codigo, justificado por comentario, impossivel pelos dados ou ja corrigido. Leia o arquivo e a linha citada, e as secoes relevantes de REGRAS_NEGOCIO.md.',
    'Veredito: REFUTADO (prova clara de que e falso); PARCIAL (verdadeiro so em parte; diga qual); MANTIDO (nao consegui refutar). Prova: linha lida, regra citada ou evidencia. Sem prova, o veredito e MANTIDO.',
    'Achado: ' + JSON.stringify(f),
  ].join('\n')
}

function promptRefutador2(f, r1) {
  return [
    CONTEXTO,
    '',
    'Papel: SEGUNDO REFUTADOR (rodada 2). Recebe o achado e o veredito da rodada 1. Tente DERRUBAR o veredito da rodada 1: se ela refutou um achado real, prove; se manteve um achado falso, prove. Mesmo criterio de veredito e prova.',
    'Achado: ' + JSON.stringify(f),
    'Rodada 1: ' + JSON.stringify(r1),
  ].join('\n')
}

function promptPropoe(f) {
  return [
    CONTEXTO,
    '',
    'Papel: PROPOSITOR DE EDICAO. Achado mantido: ' + JSON.stringify(f),
    'Leia o arquivo inteiro antes de propor. Produza um diff unificado MINIMO, no formato git (cabecalho --- a/<arquivo> e +++ b/<arquivo>), que corrige somente o trecho do achado.',
    'Contrato: nao renomeie, nao reordene e nao remova colunas de saida (contrato com validators, extract_*.py e Dashboard). Nao mude regra de negocio.',
    'Se a correcao exigir mudar contrato ou regra, ou nao for segura sem rodar no banco, responda nao_aplicavel=true com o motivo e patch vazio.',
  ].join('\n')
}

function promptRefutaEdicao(f, edicao) {
  return [
    CONTEXTO,
    '',
    'Papel: REFUTADOR DE EDICAO. Tente mostrar que o patch abaixo e INADEQUADO: (a) muda o resultado em algum caso de borda (NULL, zero, data, status); (b) quebra o contrato de colunas (nome ou ordem); (c) regride desempenho (subconsulta por linha, funcao por linha). Qualquer quebra de contrato e REPROVADA.',
    'Veredito APROVADA ou REPROVADA, com prova.',
    'Achado: ' + JSON.stringify(f),
    'Patch: ' + edicao.patch,
  ].join('\n')
}

function promptGate(f, edicao, idPatch) {
  const pasta = SCRATCH + '\\gates\\' + idPatch
  return [
    'Papel: GATE DETERMINISTICO. Nao interprete: execute os passos e relate a saida. Nao altere nenhum arquivo do repositorio.',
    'Arquivo alvo (relativo a ' + REPO + '): ' + f.arquivo,
    '1. Grave o patch em ' + SCRATCH + '\\gates\\' + idPatch + '.patch (Write, conteudo exato abaixo).',
    '2. patch_aplica: git -C ' + REPO + ' apply --check ' + SCRATCH + '\\gates\\' + idPatch + '.patch  (exit 0 = true). Nao aplica nada.',
    '3. Copia de teste: crie ' + pasta + ' e copie ' + REPO + '\\' + f.arquivo + ' para ' + pasta + '\\' + f.arquivo + ' (mantenha a estrutura de pastas). Aplique o patch dentro da copia (cwd = copia; se git recusar fora do repositorio, use patch -p1). Se nao conseguir aplicar, patch_aplica = false.',
    '4. encoding_ok: python decodifica o arquivo da copia como UTF-8 e nao tem BOM (' + REPO + '\\.venv\\Scripts\\python.exe).',
    '5. perf_ok: pwsh -NoProfile -ExecutionPolicy Bypass -Command "& \'' + REPO + '\\Tools\\Test-SqlPerformance.ps1\' -RootPath \'' + pasta + '\' -Paths @(\'' + f.arquivo + '\')"  (exit 0 = true). Atencao: -Paths precisa ser array; pwsh -File nao vincula arrays.',
    '6. saida_resumida: ultimas 15 linhas de cada comando.',
    'Conteudo exato do patch (passo 1):',
    edicao.patch,
  ].join('\n')
}

function promptEscrita(caminho, conteudo, observacao) {
  return [
    'Papel: PERSISTENCIA. Nao reinterprete nem resuma. Use a ferramenta Write para criar o arquivo ' + caminho + ' com EXATAMENTE o conteudo entre as marcas abaixo (sem alterar, sem acrescentar, sem remover linhas).',
    observacao,
    '<<<CONTEUDO',
    conteudo,
    'CONTEUDO>>>',
    'Retorne arquivos_escritos = 1.',
  ].join('\n')
}

// ---------------------------------------------------------------- Inventario
phase('Inventario')
const inventarioBruto = await parallel(
  LOTES.map((lote, i) => () =>
    agent(promptInventario(lote), {
      label: 'inventario:' + (i + 1),
      phase: 'Inventario',
      schema: SCHEMA_INVENTARIO,
      model: 'haiku',
    })
  )
)
const inventario = inventarioBruto
  .filter(Boolean)
  .flatMap((r) => r.linhas)
  .sort((a, b) => cmp(a.arquivo, b.arquivo))
const lotesSemInventario = inventarioBruto.filter((r) => !r).length
if (lotesSemInventario) log('ATENCAO: ' + lotesSemInventario + ' lotes de inventario sem resultado')
log('inventario: ' + inventario.length + ' linhas')

// ---------------------------------------------------------------- Auditar
phase('Auditar')
const tarefas = []
for (const eixo of EIXOS) {
  for (const lote of LOTES) tarefas.push({ eixo, lote })
}
const auditBruto = await parallel(
  tarefas.map((t, i) => () => {
    const nomes = new Set(t.lote.map((a) => a.arquivo))
    const invLote = inventario.filter((x) => nomes.has(x.arquivo))
    return agent(promptAuditoria(t.eixo, t.lote, invLote), {
      label: 'auditar:' + t.eixo.key + ':' + (i + 1),
      phase: 'Auditar',
      schema: SCHEMA_AUDITORIA,
      model: 'haiku',
    })
  })
)

const brutos = []
let auditoriasSemResultado = 0
auditBruto.forEach((r, i) => {
  if (!r) {
    auditoriasSemResultado += 1
    return
  }
  for (const f of r.achados) {
    brutos.push({ ...f, eixo: tarefas[i].eixo.key, escopo: ESCOPO.get(chaveArquivo(f.arquivo)) || 'acervo' })
  }
})
if (auditoriasSemResultado) log('ATENCAO: ' + auditoriasSemResultado + ' auditorias sem resultado')

// Deduplicacao e forca de regras fixas (producao sempre critica).
const vistos = new Set()
const unicos = []
for (const f of brutos) {
  if (f.escopo === 'producao') f.severidade = 'critica'
  const chave = f.arquivo + '|' + f.linha + '|' + String(f.titulo).trim().toLowerCase().slice(0, 80)
  if (vistos.has(chave)) continue
  vistos.add(chave)
  unicos.push(f)
}
const ORDEM_SEV = { critica: 0, alta: 1, media: 2, baixa: 3 }
unicos.sort(
  (a, b) =>
    ORDEM_SEV[a.severidade] - ORDEM_SEV[b.severidade] ||
    cmp(a.arquivo, b.arquivo) ||
    a.linha - b.linha ||
    cmp(a.titulo, b.titulo)
)
const analisados = unicos.slice(0, MAX_ACHADOS)
const cortados = unicos.slice(MAX_ACHADOS)
analisados.forEach((f, i) => {
  f.id = 'A' + String(i + 1).padStart(3, '0')
})
log(brutos.length + ' achados brutos, ' + unicos.length + ' unicos, ' + analisados.length + ' analisados')
if (cortados.length) {
  log('CORTE: ' + cortados.length + ' achados fora do teto de ' + MAX_ACHADOS + ' (listados em achados.md como nao analisados)')
}

// ---------------------------------------------------------------- Refutar (duas rodadas)
phase('Refutar')
const refutados = await pipeline(
  analisados,
  (f) =>
    agent(promptRefutador1(f), {
      label: f.id + ':refutar-1',
      phase: 'Refutar',
      schema: SCHEMA_REFUTACAO,
      model: 'haiku',
    }).then((r1) => ({ f, r1 })),
  (prev) => {
    if (!prev || !prev.r1) return { f: prev && prev.f, r1: null, r2: null }
    return agent(promptRefutador2(prev.f, prev.r1), {
      label: prev.f.id + ':refutar-2',
      phase: 'Refutar',
      schema: SCHEMA_REFUTACAO,
      model: 'haiku',
    }).then((r2) => ({ f: prev.f, r1: prev.r1, r2 }))
  }
)

const porId = new Map()
for (const x of refutados) {
  if (x && x.f) porId.set(x.f.id, x)
}
const veredito = analisados.map((f) => {
  const x = porId.get(f.id)
  const final = x && x.r2 ? x.r2 : x && x.r1 ? x.r1 : null
  const r1 = x && x.r1 ? x.r1.veredito : 'sem'
  const r2 = x && x.r2 ? x.r2.veredito : 'sem'
  return {
    f,
    final,
    duvida: r1 !== r2 ? 'rodadas divergiram: ' + r1 + ' -> ' + r2 : '',
  }
})

// ---------------------------------------------------------------- Editar
phase('Editar')
const elegiveis = veredito.filter(
  (v) => v.final && v.final.veredito === 'MANTIDO' && v.f.classe === 'FATO' && v.f.escopo !== 'producao'
)
const propostas = await parallel(
  elegiveis.map((v) => () =>
    agent(promptPropoe(v.f), {
      label: v.f.id + ':propor',
      phase: 'Editar',
      schema: SCHEMA_EDICAO,
      model: 'haiku',
    }).then((edicao) => ({ ...v, edicao }))
  )
)
const comPatch = propostas.filter((x) => x && x.edicao && !x.edicao.nao_aplicavel && x.edicao.patch)
const refEdicao = await parallel(
  comPatch.map((x) => () =>
    agent(promptRefutaEdicao(x.f, x.edicao), {
      label: x.f.id + ':refutar-edicao',
      phase: 'Editar',
      schema: SCHEMA_REFUTA_EDICAO,
      model: 'haiku',
    }).then((rv) => ({ ...x, refEdicao: rv }))
  )
)

// ---------------------------------------------------------------- Gates
phase('Gates')
const aprovadas = refEdicao.filter((x) => x && x.refEdicao && x.refEdicao.veredito === 'APROVADA')
const gates = await parallel(
  aprovadas.map((x, i) => () =>
    agent(promptGate(x.f, x.edicao, x.f.id), {
      label: x.f.id + ':gate',
      phase: 'Gates',
      schema: SCHEMA_GATE,
      model: 'haiku',
    }).then((g) => ({ ...x, gate: g }))
  )
)
const gatePorId = new Map()
for (const g of gates) {
  if (g && g.f) gatePorId.set(g.f.id, g)
}

// ---------------------------------------------------------------- Julgar (regra fixa, sem agente)
phase('Julgar')
const DUPLICATA = /duplic|consolid|mesma regra|nome enganoso|sinonimo/i

function destinoDe(v) {
  const f = v.f
  const final = v.final
  const base = {
    id: f.id,
    arquivo: f.arquivo,
    linha: f.linha,
    escopo: f.escopo,
    classe: f.classe,
    severidade: f.severidade,
    titulo: f.titulo,
    evidencia: f.evidencia,
    veredito: final ? final.veredito : 'sem_veredito',
    prova: final ? final.prova : '',
    duvida: v.duvida,
  }
  if (!final) return { ...base, destino: 'pergunta', motivo: 'refutadores sem resultado' }
  if (final.veredito === 'REFUTADO') return { ...base, destino: 'descartado', motivo: 'refutado na rodada final' }
  if (f.escopo === 'producao') return { ...base, destino: 'achado', motivo: 'producao: somente leitura, sem patch' }
  if (f.classe === 'DECISAO_AREA') return { ...base, destino: 'pergunta', motivo: 'decisao da area' }
  if (f.classe === 'VERIFICAR_ORACLE') return { ...base, destino: 'comando', motivo: 'depende de dado ou plano' }
  if (DUPLICATA.test(f.titulo + ' ' + f.evidencia)) {
    return { ...base, destino: 'pergunta', motivo: 'consolidacao exige decisao da area (PROPOSTA_CONSOLIDACAO)' }
  }
  if (final.veredito === 'PARCIAL') return { ...base, destino: 'achado', motivo: 'parcial: duvida registrada, sem patch' }
  const g = gatePorId.get(f.id)
  const rv = g ? g.refEdicao : null
  const e = (propostas.find((p) => p && p.f && p.f.id === f.id) || {}).edicao
  if (rv && rv.veredito === 'REPROVADA') {
    return { ...base, destino: 'pergunta', motivo: 'patch reprovado na refutacao de edicao: ' + rv.prova }
  }
  if (g && g.gate && g.gate.patch_aplica && g.gate.encoding_ok && g.gate.perf_ok) {
    return {
      ...base,
      destino: 'edicao',
      motivo: 'patch aprovado na refutacao e nos gates offline; validacao Oracle pendente',
      patch: g.edicao.patch,
      gate: g.gate.saida_resumida,
    }
  }
  if (g && g.gate) return { ...base, destino: 'pergunta', motivo: 'gate offline reprovou o patch' }
  return { ...base, destino: 'achado', motivo: e && e.nao_aplicavel ? 'sem correcao segura: ' + e.motivo : 'sem patch' }
}

const julgados = veredito.map(destinoDe)
for (const c of cortados) {
  julgados.push({
    id: 'N/A',
    arquivo: c.arquivo,
    linha: c.linha,
    escopo: c.escopo,
    classe: c.classe,
    severidade: c.severidade,
    titulo: c.titulo,
    evidencia: c.evidencia,
    veredito: 'nao_analisado',
    prova: '',
    duvida: '',
    destino: 'nao_analisado',
    motivo: 'fora do teto de ' + MAX_ACHADOS,
  })
}
const porDestino = {}
for (const j of julgados) porDestino[j.destino] = (porDestino[j.destino] || 0) + 1
log('destinos: ' + JSON.stringify(porDestino))

// ---------------------------------------------------------------- Escrever (conteudo montado aqui; agentes so gravam)
phase('Escrever')

const linhasInv = inventario.map(
  (x) =>
    '| ' + cel(x.arquivo) + ' | ' + cel(x.pasta) + ' | ' + cel(x.tabelas.join(', ')) + ' | ' +
    cel(x.colunas_saida.join(', ')) + ' | ' + (x.sonda_literal_fixo ? 'sim' : 'nao') + ' | ' +
    (x.tem_order_by ? 'sim' : 'nao') + ' | ' + cel(x.observacao) + ' |'
)
const invMd = [
  '# Inventario do acervo SQL - ' + DATA,
  '',
  'Total: ' + inventario.length + ' consultas. Escopo: acervo (212 em 01-10, 13), runtime das automacoes e producao (somente leitura). 11_views_referencia_sgt e 12_manutencao_dml_restrito sao contexto, nao inventariados.',
  '',
  '| arquivo | pasta | tabelas | colunas_saida | sonda_literal | tem_order_by | observacao |',
  '|---|---|---|---|---|---|---|',
  ...linhasInv,
  '',
].join('\n')
const invJson = JSON.stringify(inventario, null, 2) + '\n'

const linhasAch = julgados.map(
  (j) =>
    '| ' + cel(j.id) + ' | ' + cel(j.arquivo) + ':' + cel(j.linha) + ' | ' + cel(j.escopo) + ' | ' +
    cel(j.severidade) + ' | ' + cel(j.classe) + ' | ' + cel(j.veredito) + ' | ' + cel(j.destino) + ' | ' +
    cel(j.titulo) + ' | ' + cel(j.prova) + ' | ' + cel(j.duvida) + ' |'
)
const achMd = [
  '# Achados do acervo SQL - ' + DATA,
  '',
  'Pipeline: inventario -> 4 eixos -> deduplicacao -> 2 rodadas de refutacao -> edicao (so FATO mantido) -> refutacao de edicao -> gates offline -> juiz deterministico. Nada foi aplicado ao SQL de producao.',
  '',
  'Totais por destino: ' + JSON.stringify(porDestino),
  '',
  '| id | arquivo:linha | escopo | severidade | classe | veredito final | destino | titulo | prova | duvida |',
  '|---|---|---|---|---|---|---|---|---|---|',
  ...linhasAch,
  '',
].join('\n')

const comandos = [
  '# Comandos Oracle para rodar na sua maquina (na ordem)',
  '',
  'Data: ' + DATA + '. Rodar da raiz ' + REPO + ' com o venv do projeto. Nenhum comando abaixo altera SQL de producao; o validador so faz parse e smoke de 1 linha.',
  '',
  '## 1. Validar o acervo (parse e smoke)',
  '',
  '.venv/Scripts/python Tools/oracle/validar_sql_oracle.py --root docs/oracle-schema/consultas --out ' + SAIDA + '/evidencia/validar-acervo.json',
  '',
  '## 2. Varredura de desempenho e falhas',
  '',
  '.venv/Scripts/python Tools/oracle/auditar_acervo_sql.py --out ' + SAIDA + '/evidencia/varredura.json',
  '',
  '## 3. Para cada edicao em edicoes/ (uma por vez)',
  '',
  'a) Medir o controle (original): .venv/Scripts/python Tools/oracle/medir_sql_oracle.py <arquivo original> --runs 5 --dump ' + SAIDA + '/evidencia/<id>-controle.json --out ' + SAIDA + '/evidencia/<id>-medicao-controle.json',
  'b) Aplicar o patch em uma copia (teste com git apply --check antes) e medir a candidata com --dump ' + SAIDA + '/evidencia/<id>-candidata.json.',
  'c) Comparar: .venv/Scripts/python Tools/oracle/comparar_equivalencia.py --controle ' + SAIDA + '/evidencia/<id>-controle.json --candidata ' + SAIDA + '/evidencia/<id>-candidata.json --chaves <chaves do GRAO no cabecalho do SQL> --relatorio ' + SAIDA + '/evidencia/<id>-equivalencia.json',
  '',
  '## 4. Gates offline (depois de aplicar as edicoes aprovadas)',
  '',
  '.venv/Scripts/python Tools/oracle/gerar_catalogo_sql.py --check',
  '',
  'pwsh -NoProfile -ExecutionPolicy Bypass -Command "& \'Tools/Test-SqlPerformance.ps1\' -RootPath \'.\' -Paths @(\'<arquivo alterado>\')"',
  '',
  '.venv/Scripts/python -m pytest Orchestrator/tests -q (testes dos modulos afetados)',
  '',
  'Atencao: gerar_catalogo_sql.py --evidencia so depois de validar-acervo.json existir e de as edicoes terem sido aprovadas.',
  '',
].join('\n')

const perguntas = julgados.filter((j) => j.destino === 'pergunta' || j.destino === 'comando')
const perguntasMd = [
  '# Perguntas para a area e para o Gabriel - ' + DATA,
  '',
  'DECISAO_AREA e consolidacoes vao aqui e NAO viram edicao. VERIFICAR_ORACLE vira comando de conferencia.',
  '',
  ...perguntas.map(
    (j) =>
      '## ' + j.id + ' - ' + j.arquivo + ':' + j.linha + ' (' + j.destino + ', ' + j.classe + ')\n\n' +
      '- Achado: ' + j.titulo + '\n' +
      '- Evidencia: ' + j.evidencia + '\n' +
      '- Motivo do destino: ' + j.motivo + '\n' +
      (j.destino === 'comando' ? '- Conferir no Oracle e registrar o resultado.\n' : '- Pergunta: decidir se esta regra deve mudar, e como.\n') +
      ''
  ),
  perguntas.length ? '' : '_Nenhum item nesta rodada._',
  '',
].join('\n')

const edicoes = julgados.filter((j) => j.destino === 'edicao')
const edicoesMd = edicoes.map((j) => '- ' + j.id + ' ' + j.arquivo + ':' + j.linha + ' - ' + j.titulo + ' (gate: ' + j.gate + ')').join('\n')

// Os 3 escritores gravam conteudo ja pronto; cada um cuida de um grupo de arquivos.
const escritas = [
  promptEscrita(SAIDA + '/inventario.md', invMd, 'Arquivo: inventario em markdown.'),
  promptEscrita(SAIDA + '/inventario.json', invJson, 'Arquivo: inventario em JSON.'),
  promptEscrita(SAIDA + '/achados.md', achMd, 'Arquivo: achados e veredictos.'),
  promptEscrita(SAIDA + '/comandos-oracle.md', comandos, 'Arquivo: comandos para rodar na maquina do Gabriel.'),
  promptEscrita(SAIDA + '/perguntas-ao-humano.md', perguntasMd, 'Arquivo: perguntas para a area e comandos de conferencia.'),
  promptEscrita(SAIDA + '/edicoes/LEIAME.md', edicoesMd || '_Nenhuma edicao aprovada nesta rodada._', 'Arquivo: lista das edicoes candidatas (os .patch sao gravados a seguir).'),
]
for (const j of edicoes) {
  escritas.push(
    promptEscrita(
      SAIDA + '/edicoes/' + j.id + '.patch',
      j.patch,
      'Arquivo: patch candidato ' + j.id + ' (status: aprovado nos gates offline; validacao Oracle pendente).'
    )
  )
}

const resultadoEscrita = await parallel(
  escritas.map((prompt, i) => () =>
    agent(prompt, {
      label: 'escrever:' + (i + 1),
      phase: 'Escrever',
      schema: SCHEMA_ESCRITA,
      model: 'haiku',
    })
  )
)
const escritos = resultadoEscrita.filter(Boolean).reduce((s, r) => s + (r.arquivos_escritos || 0), 0)
const falhasEscrita = resultadoEscrita.filter((r) => !r).length
if (falhasEscrita) log('ATENCAO: ' + falhasEscrita + ' arquivos nao gravados')
log('artefatos gravados: ' + escritos + ' de ' + escritas.length)

return {
  data: DATA,
  pasta: SAIDA,
  inventario: inventario.length,
  brutos: brutos.length,
  unicos: unicos.length,
  analisados: analisados.length,
  cortados: cortados.length,
  destinos: porDestino,
  artefatosGravados: escritos,
  artefatosPlanejados: escritas.length,
}
