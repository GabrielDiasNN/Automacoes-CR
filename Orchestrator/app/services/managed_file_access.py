"""Acesso seguro a arquivos gerenciados de automações (config e IDE).

Capacidade compartilhada pelos routers ``automation_config`` e
``automation_ide``. Antes vivia como funções privadas em ``routers/automations``
— que sequer as consumia — obrigando os dois routers a importar privados de um
terceiro router (achado #32).

As guardas aqui são de segurança (path traversal por nome, por symlink e por
escape do PROJECT_ROOT); alterações devem preservar os testes de escape em
``tests/test_automations_ide.py`` e ``tests/test_automations_crud.py``.
"""

from __future__ import annotations

import os

from fastapi import HTTPException

from ..utils import backup_timestamped_file, timestamp_suffix


def resolve_automation_dir(script_path: str, project_root: str) -> str:
    """Resolve a pasta da automacao garantindo permanencia no ``project_root``."""
    if script_path.startswith("./") or script_path.startswith(".\\"):
        resolved_script = os.path.join(project_root, script_path[2:])
    elif not os.path.isabs(script_path):
        resolved_script = os.path.join(project_root, script_path)
    else:
        resolved_script = script_path

    auto_dir = os.path.dirname(os.path.abspath(os.path.normpath(resolved_script)))
    root_abs = os.path.abspath(os.path.normpath(project_root))
    try:
        if os.path.commonpath([root_abs, auto_dir]) != root_abs:
            raise HTTPException(
                status_code=403, detail="Diretorio da automacao fora do projeto."
            )
    except ValueError as exc:
        # commonpath levanta ValueError para drives distintos no Windows.
        raise HTTPException(
            status_code=403, detail="Diretorio da automacao fora do projeto."
        ) from exc
    return auto_dir


def resolve_managed_file(auto_dir: str, filename: str) -> str:
    """Resolve arquivo gerenciado impedindo path traversal por nome ou symlink."""
    if os.path.basename(filename) != filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")

    target_path = os.path.abspath(os.path.normpath(os.path.join(auto_dir, filename)))
    auto_dir_abs = os.path.abspath(os.path.normpath(auto_dir))
    if os.path.commonpath([auto_dir_abs, target_path]) != auto_dir_abs:
        raise HTTPException(status_code=403, detail="Acesso negado ao arquivo.")
    if not os.path.exists(target_path) or not os.path.isfile(target_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return target_path


def backup_file_before_write(target_path: str, auto_dir: str) -> str:
    """Cria backup local antes de sobrescrever arquivo gerenciado."""
    backup_dir = os.path.join(auto_dir, ".orchestrator_backups")
    backup_name = f"{os.path.basename(target_path)}.{timestamp_suffix()}.bak"
    backup_path = backup_timestamped_file(target_path, backup_dir, backup_name)
    return os.path.relpath(backup_path, auto_dir)
