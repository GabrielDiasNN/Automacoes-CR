#!/bin/bash
# Hook SessionStart: prepara o ambiente de sessões em nuvem (Linux).
# Só roda em ambiente remoto; na máquina Windows do operador sai sem fazer nada.
# Idempotente e não interativo. Falha de pwsh é tolerada (aviso); falha de Python/Node derruba o hook.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Python: virtualenv na raiz (.venv), igual à máquina do operador, instalado pelos locks com hash.
# Python 3.12 é o do CI (governanca.yml); os locks fixam versões que exigem >=3.12 (ex.: numpy).
# Um .venv antigo com Python < 3.12 (criado por hook anterior) e recriado: os locks nao instalam nele.
if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  rm -rf .venv
fi
if [ ! -x .venv/bin/python ]; then
  "$(command -v python3.12 || command -v python3)" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --disable-pip-version-check \
  -r requirements.txt -r requirements-test.txt -r requirements-dev.txt
# ruff não está nos locks; o CI o instala pinado (governanca.yml), então o hook também.
.venv/bin/python -m pip install --quiet --disable-pip-version-check ruff==0.16.6

# Dashboard: `npm install` pode reescrever Dashboard/package-lock.json e sujar a arvore; por isso `npm ci`,
# so quando node_modules falta ou o lock e mais novo que o instalado (idempotente, aproveita o cache do conteiner).
if [ ! -f Dashboard/node_modules/.package-lock.json ] \
  || [ Dashboard/package-lock.json -nt Dashboard/node_modules/.package-lock.json ]; then
  npm ci --prefix Dashboard --no-audit --no-fund --silent
fi

# PowerShell 7: hooks, gates de governança e skills do repo são .ps1. Melhor esforço.
if ! command -v pwsh >/dev/null 2>&1; then
  # Cadeia com && (e nao set -e): em `( ... ) || echo`, o set -e fica desligado dentro do subshell e o
  # status seria o do ultimo comando, escondendo a falha.
  (
    . /etc/os-release \
      && tmp="$(mktemp --suffix=.deb)" \
      && curl -fsSL "https://packages.microsoft.com/config/${ID}/${VERSION_ID}/packages-microsoft-prod.deb" -o "$tmp" \
      && dpkg -i "$tmp" >/dev/null \
      && rm -f "$tmp" \
      && apt-get update -qq \
      && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq powershell >/dev/null
  ) || echo "AVISO: não foi possível instalar o pwsh; hooks e gates PowerShell não rodarão nesta sessão." >&2
fi

# Tools/ValidarAutomacoes.ps1 chama `powershell` (PS 5.1 do Windows); no Linux o alias aponta para o pwsh,
# senão a etapa de skills do gate de governança (inclusive o hook Stop) falha por ambiente.
# `powershell.exe` também: os testes de lib/tests disparam esse nome via Start-Process.
if command -v pwsh >/dev/null 2>&1; then
  for alias_name in powershell powershell.exe; do
    if ! command -v "$alias_name" >/dev/null 2>&1; then
      ln -s "$(command -v pwsh)" "/usr/local/bin/$alias_name" 2>/dev/null \
        || echo "AVISO: não foi possível criar o alias '$alias_name'; o gate de governança e parte dos testes de lib/tests falharão nesta sessão." >&2
    fi
  done
fi

# Módulos PowerShell dos gates: Pester 5.7.1 (versão do CI) e PSScriptAnalyzer (Test-PowerShellGovernance).
# O PSGallery pode estar fora da lista de domínios permitidos do ambiente; nesse caso o Pester vem do NuGet
# (api.nuget.org) e o PSScriptAnalyzer, que só existe no PSGallery, vira aviso.
if command -v pwsh >/dev/null 2>&1; then
  modules_dir="$HOME/.local/share/powershell/Modules"
  if ! pwsh -NoProfile -Command "if (Get-Module -ListAvailable Pester | Where-Object Version -eq '5.7.1') { exit 0 } else { exit 1 }"; then
    # && em vez de set -e (ver acima); so conta como sucesso com Pester.psd1 extraido, e a falha limpa o diretorio.
    (
      pester_dir="$modules_dir/Pester/5.7.1" \
        && mkdir -p "$pester_dir" \
        && tmp="$(mktemp --suffix=.nupkg)" \
        && curl -fsSL "https://api.nuget.org/v3-flatcontainer/pester/5.7.1/pester.5.7.1.nupkg" -o "$tmp" \
        && python3 -c "import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$tmp" "$pester_dir" \
        && cp -r "$pester_dir/tools/." "$pester_dir/" \
        && rm -f "$tmp" \
        && test -f "$pester_dir/Pester.psd1"
    ) || {
      rm -rf "$modules_dir/Pester/5.7.1"
      echo "AVISO: não foi possível instalar o Pester 5.7.1; os testes de lib/tests não rodarão nesta sessão." >&2
    }
  fi
  if ! pwsh -NoProfile -Command "if (Get-Module -ListAvailable PSScriptAnalyzer) { exit 0 } else { exit 1 }"; then
    pwsh -NoProfile -Command "
      \$ErrorActionPreference = 'Stop'
      if (-not (Get-PSRepository -Name PSGallery -ErrorAction SilentlyContinue)) { Register-PSRepository -Default }
      Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
      Install-Module -Name PSScriptAnalyzer -Scope CurrentUser -Force" >/dev/null 2>&1 \
      || echo "AVISO: PSScriptAnalyzer não instalado (libere www.powershellgallery.com e cdn.powershellgallery.com na rede do ambiente); Test-PowerShellGovernance ficará sem análise estática." >&2
  fi
fi

# Faz o Python do projeto ser o padrão da sessão.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$PWD/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
