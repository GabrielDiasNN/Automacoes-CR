export const meta = {
  name: 'revisao-sql-producao-oracle',
  description: 'Revisa o SQL de producao contra o Oracle - somente leitura: paridade de saida com o HEAD, desempenho medido e decisao por regra fixa. Altera SQL so com aprovacao explicita.',
  whenToUse: 'Revisao de SQL de producao das automacoes depois de uma reescrita nao commitada, ou periodicamente. Nao commita nada.',
  phases: [
    { title: 'Validar', detail: 'por unidade, em sequencia: parse, medicao de 7 execucoes, dump do resultado e comparacao com o HEAD' },
    { title: 'Decidir', detail: 'regra fixa: manter a versao de trabalho so se a saida for igual ao HEAD e a medicao for MELHORA' },
    { title: 'Aplicar', detail: 'so com args.aplicar = true: restaura o HEAD onde a decisao pede e preserva a versao de trabalho em evidencia' },
    { title: 'Verificar', detail: 'parse e equivalencia da versao final, e gates offline - Test-SqlPerformance e testes de custo' },
  ],
}

const SCHEMA_UNIDADE = {
  type: 'object',
  properties: {
    unidade: { type: 'string' },
    parse_ok: { type: 'boolean' },
    guard_ok: { type: 'boolean' },
    excecao_guard: { type: 'boolean' },
    linhas_head: { type: 'integer' },
    linhas_wt: { type: 'integer' },
    mediana_head_ms: { type: 'number' },
    ruido_head_ms: { type: 'number' },
    mediana_wt_ms: { type: 'number' },
    ruido_wt_ms: { type: 'number' },
    equivalente: { type: 'boolean' },
    divergencias: { type: 'integer' },
    veredito_medicao: { type: 'string' },
    sem_ponto_e_virgula_final: { type: 'boolean' },
    erros: { type: 'string' },
    observacoes: { type: 'string' },
  },
  required: ['unidade', 'parse_ok', 'guard_ok', 'sem_ponto_e_virgula_final', 'observacoes'],
}

const PY = '.venv/Scripts/python.exe'
const REGRAS_COMUNS = [
  'Regras obrigatorias: so leitura no Oracle (SELECT, EXPLAIN PLAN com rollback). Nunca faca COMMIT, DML fora da PLAN_TABLE ou DDL.',
  'Nunca altere arquivos .sql nem o working tree. Nunca imprima credenciais, DSN ou o conteudo do .env.',
  'Use PYTHONUTF8=1 em todos os comandos Python. Se um comando falhar, copie o erro exato no campo erros e siga para o proximo passo.',
  'Responda somente com o objeto estruturado pedido.',
].join('\n')

function promptValidar(u, dir) {
  // head_path/wt_path: caminhos ja renderizados para templates com marcadores (ex.: /*IN_BINDS*/).
  const head = u.head_path || `${dir}/evidencia/head/${u.nome}.sql`
  const wt = u.wt_path || `${dir}/evidencia/wt/${u.nome}.sql`
  const binds = (u.binds || []).map((b) => `--bind ${b}`).join(' ')
  const priv = `${dir}/evidencia/dump-priv.json`
  const saida = `${dir}/evidencia/unidades/${u.id}`
  const medir = (arq, rel, dump, extra) =>
    `PYTHONUTF8=1 ${PY} Tools/oracle/medir_sql_oracle.py "${arq}" --runs 7 --timeout 900 ${extra} ${binds} --dump "${dump}" --out "${rel}"`
  const extraFuncao = u.funcoes ? `--aceitar-funcoes-somente-leitura "${priv}"` : ''
  const comparacao = u.tem_wt_diferente
    ? `PYTHONUTF8=1 ${PY} Tools/oracle/comparar_equivalencia.py --controle "${saida}-head-dump.json" --candidata "${saida}-wt-dump.json"${u.colunas_comparadas ? ` --colunas "${u.colunas_comparadas}"` : ''} --relatorio "${saida}-equivalencia.json"`
    : 'nao se aplica (HEAD e versao de trabalho sao identicos)'
  return `Unidade ${u.id} (${u.arquivo}). Diretorio de trabalho: a raiz do repositorio.
${REGRAS_COMUNS}

Passos, nesta ordem:
0. Verificacao do texto cru, que e o que o runner de producao executa (validar e medir normalizam e removem o ponto e virgula final, por isso esta checagem e obrigatoria):
   tail -n 1 "${wt}" (ignore linhas vazias) e grep -n ";" "${wt}". sem_ponto_e_virgula_final = true somente se a ultima linha nao vazia nao terminar com ";" e nao houver ";" fora de comentarios e literais.
1. Parse e smoke da versao de trabalho:
   PYTHONUTF8=1 ${PY} Tools/oracle/validar_sql_oracle.py --root "${dir}/evidencia/wt" --file "${wt}" --out "${saida}-validar-wt.json"
   Leia o JSON e marque parse_ok = (status == "validated").
2. Medir o HEAD (controle) e a versao de trabalho, 7 execucoes cada, com dump:
   ${medir(head, `${saida}-head-medicao.json`, `${saida}-head-dump.json`, extraFuncao)}
   ${u.tem_wt_diferente ? medir(wt, `${saida}-wt-medicao.json`, `${saida}-wt-dump.json`, extraFuncao) : '(sem medicao da versao de trabalho: arquivo identico ao HEAD)'}
   Leia os relatorios: summary.median_ms e summary.noise_ms de cada um, e as linhas de runs[0].rows. Se algum relatorio tiver "excecao_guard", marque excecao_guard = true. Se o guard bloquear sem excecao, marque guard_ok = false e copie a saida do guard em erros.
3. Comparar a saida (somente se a versao de trabalho for diferente):
   ${comparacao}
   Leia o relatorio: equivalente = true se nao houver divergencia; divergencias = numero de divergencias.
4. veredito_medicao: copie o campo de veredito do relatorio da versao de trabalho quando existir (MELHORA, NEUTRO ou PIORA), senao "nao medido".

Preencha o objeto com os valores lidos dos arquivos. Nao estime valores.`
}

function promptVerificar(u, dir) {
  const saida = `${dir}/evidencia/unidades/${u.id}`
  const pasta = u.arquivo_repo.split('/').slice(0, -1).join('/')
  return `Verificacao final da unidade ${u.id} (${u.arquivo_repo}). Diretorio de trabalho: a raiz do repositorio.
${REGRAS_COMUNS}

1. Parse e smoke do arquivo final que esta no working tree:
   PYTHONUTF8=1 ${PY} Tools/oracle/validar_sql_oracle.py --root "${pasta}" --file "${u.arquivo_repo}" --out "${saida}-validar-final.json"
   parse_ok = true quando o JSON mostrar parse = pass e smoke = pass, inclusive quando o status for blocked_custom_function por chamada de funcao de pacote (isso e uma restricao do guard, nao falha de parse). Marque false nos demais casos e copie o erro do Oracle em erros.
   Atencao: um erro ORA-00936 com marcador /*IN_BINDS*/ ou /*FIN_BINDS*/ no SQL significa template nao renderizado, e nao defeito; o campo head_path/wt_path ja aponta para a versao renderizada.
2. Testes offline de custo e desempenho do SQL:
   pwsh -NoProfile -ExecutionPolicy Bypass -Command "& 'Tools/Test-SqlPerformance.ps1' -RootPath '.' -Paths @('${u.arquivo_repo}')"
3. Responda: parse_ok, guard_ok e observacoes com o que falhou, se houver.`
}

  // args: { aplicar: boolean, unidades: [{id, nome, arquivo, arquivo_repo, funcoes, tem_wt_diferente, colunas_ignoradas}], dir }
  const cfg = args || {}
  const dir = cfg.dir
  if (!dir || !Array.isArray(cfg.unidades) || cfg.unidades.length === 0) {
    return { erro: 'args precisa de dir e de unidades' }
  }

  // Validar: uma unidade por vez, para nao sobrecarregar o banco de producao.
  phase('Validar')
  const resultados = []
  for (const u of cfg.unidades) {
    const r = await agent(promptValidar(u, dir), {
      label: `validar:${u.id}`,
      phase: 'Validar',
      schema: SCHEMA_UNIDADE,
    })
    resultados.push({ unidade: u, resultado: r })
    log(`${u.id}: ${r ? (r.equivalente === false ? 'DIVERGE' : 'ok') : 'sem resultado'}`)
  }

  // Decidir: regra fixa, sem opiniao. Manter a versao de trabalho so com prova de paridade e ganho medido.
  phase('Decidir')
  const decisoes = resultados.map(({ unidade: u, resultado: r }) => {
    if (!r) return { id: u.id, acao: 'pendente', motivo: 'agente nao devolveu resultado' }
    if (!u.tem_wt_diferente) return { id: u.id, acao: 'manter', motivo: 'HEAD e versao de trabalho identicos' }
    if (r.sem_ponto_e_virgula_final !== true) return { id: u.id, acao: 'reverter_head', motivo: 'texto cru termina com ponto e virgula: o runner de producao falha com ORA-00933' }
    if (!r.parse_ok || !r.guard_ok) return { id: u.id, acao: 'reverter_head', motivo: 'versao de trabalho nao passa parse ou guard' }
    if (r.equivalente !== true) return { id: u.id, acao: 'reverter_head', motivo: `saida diverge do HEAD (${r.divergencias} divergencias)` }
    if (r.veredito_medicao === 'MELHORA') return { id: u.id, acao: 'manter_wt', motivo: 'saida igual ao HEAD e ganho medido' }
    // Obs.: quando a versao de trabalho muda a saida por dado vivo, a comparacao deve ser feita com as duas versoes em sequencia (ver evidencia de back-to-back).
    // Correcao aprovada pelo DBA: aceita custo de ate 2x a mediana do HEAD (ex.: determinismo do pedido).
    if (u.correcao_aprovada && r.mediana_wt_ms <= 2 * r.mediana_head_ms) return { id: u.id, acao: 'manter_wt', motivo: 'saida igual ao HEAD, correcao aprovada, custo dentro de 2x' }
    return { id: u.id, acao: 'reverter_head', motivo: `sem ganho medido (veredito: ${r.veredito_medicao})` }
  })

  if (!cfg.aplicar) {
    return { fase: 'decidido', aguardando_aprovacao: true, decisoes, resultados: resultados.map((x) => x.resultado) }
  }

  // Aplicar: so com aprovacao explicita (args.aplicar = true). Preserva a versao de trabalho em evidencia/wt.
  phase('Aplicar')
  const aplicacoes = []
  for (const d of decisoes) {
    if (d.acao !== 'reverter_head') {
      aplicacoes.push({ id: d.id, acao: d.acao })
      continue
    }
    const u = cfg.unidades.find((x) => x.id === d.id)
    const r = await agent(
      `Restaurar o HEAD no working tree para a unidade ${u.id} (${u.arquivo_repo}). Diretorio: a raiz do repositorio.
${REGRAS_COMUNS}
Passos: (1) confira que ${dir}/evidencia/wt/${u.nome}.sql e identico ao arquivo atual ${u.arquivo_repo} (sha256). Se nao for identico, pare e responda erros. (2) Restaure o conteudo do proprio Git, nunca de copia em disco (uma copia antiga sobrescreveria o arquivo com outra versao): git restore --source=HEAD --worktree -- '${u.arquivo_repo}'. Nao use redirecionamento (git show > arquivo): no PowerShell o '>' regrava o arquivo em UTF-16 ou troca os fins de linha. (3) Confirme com "git diff --quiet -- '${u.arquivo_repo}'" que o arquivo voltou ao HEAD. Nao use git checkout nem git reset.`,
      { label: `aplicar:${u.id}`, phase: 'Aplicar', schema: SCHEMA_UNIDADE }
    )
    aplicacoes.push({ id: d.id, acao: 'reverter_head', ok: !!r && !r.erros })
  }

  // Verificar: parse da versao final e gates offline.
  phase('Verificar')
  const verificacoes = []
  for (const u of cfg.unidades) {
    const r = await agent(promptVerificar(u, dir), { label: `verificar:${u.id}`, phase: 'Verificar', schema: SCHEMA_UNIDADE })
    verificacoes.push({ id: u.id, resultado: r })
  }

  return { fase: 'concluido', decisoes, aplicacoes, verificacoes: verificacoes.map((v) => ({ id: v.id, parse_ok: v.resultado ? v.resultado.parse_ok : null })) }
