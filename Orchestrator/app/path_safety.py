"""Contenção de caminhos — fonte única da guarda anti path-traversal.

Havia três implementações divergentes no repositório até 31/07/2026:

- `utils.validate_script_path` usava `abs_path.startswith(project_root)`.
  Prefixo de string não respeita fronteira de diretório: `C:\\Automacoes_bkp\\x.ps1`
  satisfaz `startswith("C:\\Automacoes")` e passava como "dentro do projeto" — e
  esse é justamente o caminho do script que o worker vai executar.
- `routers/executions.download_artifact` repetia o mesmo `startswith`.
- `services/managed_file_access` usava `commonpath` (correto quanto à fronteira),
  mas resolvia com `abspath`, que colapsa `..` apenas lexicalmente e **não**
  resolve symlinks/junctions — enquanto a docstring prometia, literalmente,
  "impedindo path traversal por nome ou symlink". Garantia documentada e
  inexistente é pior que garantia ausente: revisores confiam nela.

`realpath` é aplicado aos DOIS lados. É o que dissolve o trade-off levantado na
revisão ("e se o próprio diretório do projeto estiver atrás de uma junction?"):
com ambos resolvidos, a junction do root desaparece igualmente dos dois lados e
a comparação continua válida.
"""

from __future__ import annotations

import os


def resolve_real(path: str) -> str:
    """Caminho absoluto, com symlinks/junctions resolvidos e caixa normalizada.

    `normcase` importa no Windows, onde `c:\\automacoes` e `C:\\Automacoes` são o
    mesmo diretório mas diferem como string — a comparação por `startswith`
    rejeitava indevidamente caminhos válidos com caixa diferente.
    """
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def is_contained(root: str, target: str) -> bool:
    """`target` está dentro de `root` (ou é o próprio `root`)?

    Compara por componentes de caminho, nunca por prefixo de string.
    """
    root_real = resolve_real(root)
    target_real = resolve_real(target)
    try:
        return os.path.commonpath([root_real, target_real]) == root_real
    except ValueError:
        # commonpath levanta ValueError para drives distintos no Windows.
        return False
