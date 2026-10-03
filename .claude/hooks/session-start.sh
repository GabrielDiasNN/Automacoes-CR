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
if [ ! -x .venv/bin/python ]; then
  "$(command -v python3.12 || command -v python3)" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --disable-pip-version-check \
  -r requirements.txt -r requirements-test.txt -r requirements-dev.txt
# ruff não está nos locks; o CI o instala pinado (governanca.yml), então o hook também.
.venv/bin/python -m pip install --quiet --disable-pip-version-check ruff==0.16.6

# Dashboard: npm install (e não npm ci) para aproveitar o cache do contêiner entre sessões.
npm install --prefix Dashboard --no-audit --no-fund --silent

# PowerShell 7: hooks, gates de governança e skills do repo são .ps1. Melhor esforço.
if ! command -v pwsh >/dev/null 2>&1; then
  (
    . /etc/os-release
    tmp="$(mktemp --suffix=.deb)"
    curl -fsSL "https://packages.microsoft.com/config/${ID}/${VERSION_ID}/packages-microsoft-prod.deb" -o "$tmp"
    dpkg -i "$tmp" >/dev/null
    rm -f "$tmp"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq powershell >/dev/null
  ) || echo "AVISO: não foi possível instalar o pwsh; hooks e gates PowerShell não rodarão nesta sessão." >&2
fi

# Tools/ValidarAutomacoes.ps1 chama `powershell` (PS 5.1 do Windows); no Linux o alias aponta para o pwsh,
# senão a etapa de skills do gate de governança (inclusive o hook Stop) falha por ambiente.
if command -v pwsh >/dev/null 2>&1 && ! command -v powershell >/dev/null 2>&1; then
  ln -s "$(command -v pwsh)" /usr/local/bin/powershell 2>/dev/null \
    || echo "AVISO: não foi possível criar o alias 'powershell'; o gate de governança falhará nesta sessão." >&2
fi

# Faz o Python do projeto ser o padrão da sessão.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$PWD/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
