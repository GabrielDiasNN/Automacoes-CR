# pylint: disable=broad-exception-caught
# mypy: ignore-errors
"""
Ferramenta de Diagnóstico - Hub de Automações.
Valida saúde do banco de Dados, API do agendador e integridade de logs.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

import requests

# Caminhos Padronizados
BASE_DIR = r"c:\Automacoes"
DB_PATH = os.path.join(BASE_DIR, "Orchestrator", "automacoes.db")
ENV_PATH = os.path.join(BASE_DIR, ".env")


def get_api_key() -> Optional[str]:
    """Recupera a API Key do arquivo .env."""
    try:
        if not os.path.exists(ENV_PATH):
            return None
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "ORCHESTRATOR_API_KEY=" in line:
                    return line.split("=")[1].strip().strip('"').strip("'")
    except Exception:
        return None
    return None


def check_db_health() -> None:
    """Verifica a integridade e estado das tabelas do banco de dados SQLite."""
    print("\n[1] Verificando Saúde do Banco de Dados...")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"   - Tabelas encontradas: {', '.join(tables)}")

        cursor.execute("SELECT count(*) FROM automations WHERE enabled=1")
        active = cursor.fetchone()[0]
        print(f"   - Automações habilitadas: {active}")

        cursor.execute(
            "SELECT count(*) FROM executions WHERE status IN ('PENDING', 'RUNNING')"
        )
        running = cursor.fetchone()[0]
        print(f"   - Tarefas ativas (PENDING/RUNNING): {running}")

        cursor.execute("SELECT last_ping FROM worker_heartbeat")
        ping = cursor.fetchone()
        print(f"   - Último Heartbeat do Worker: {ping[0] if ping else 'N/A'}")

        conn.close()
    except Exception as e:
        print(f"   - ERRO no Banco: {e}")


def check_scheduler_api() -> None:
    """Verifica se o agendador está respondendo via API REST."""
    print("\n[2] Verificando Agendador via API...")
    api_key = get_api_key()
    if not api_key:
        print("   - ERRO: API_KEY não encontrada no .env")
        return

    try:
        r = requests.get(
            "http://localhost:8000/api/system/scheduler/jobs",
            headers={"X-API-Key": api_key},
            timeout=5,
        )
        if r.status_code == 200:
            jobs = r.json()
            print(f"   - Total de Jobs no APScheduler: {len(jobs)}")
            for j in jobs:
                print(
                    f"     > {j['id']} ({j['automation_name']}): "
                    f"Próximo disparo em {j['next_run_time']}"
                )
        else:
            print(f"   - API retornou status {r.status_code}")
    except Exception as e:
        print(f"   - ERRO ao conectar na API: {e} (O Orquestrador está online?)")


def check_recent_logs() -> None:
    """Analisa o arquivo de log do orquestrador em busca de erros recentes."""
    print("\n[3] Analisando Logs Recentes (Últimos 10 erros)...")
    log_path = os.path.join(BASE_DIR, "Orchestrator", "Logs", "orchestrator.log")
    if not os.path.exists(log_path):
        print("   - Arquivo de log não encontrado.")
        return

    try:
        errors = []
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in reversed(lines):
                try:
                    data = json.loads(line)
                    if data.get("level") in ["ERROR", "CRITICAL"]:
                        errors.append(f"[{data['ts']}] {data['msg']}")
                    if len(errors) >= 10:
                        break
                except (json.JSONDecodeError, KeyError):
                    continue

        if errors:
            for err in errors:
                print(f"   - {err}")
        else:
            print("   - Nenhum erro recente encontrado nos logs JSON.")
    except Exception as e:
        print(f"   - ERRO ao ler logs: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("FERRAMENTA DE DIAGNÓSTICO - HUB DE AUTOMAÇÕES v1.0")
    print(f"Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    check_db_health()
    check_scheduler_api()
    check_recent_logs()

    print("\n" + "=" * 60)
