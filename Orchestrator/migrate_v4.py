"""
Script de Migracao v4.0 — Preserva dados existentes e cria novas tabelas.

Seguro para executar multiplas vezes (idempotente).
"""

import os
import sqlite3
import sys
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "automacoes.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print("[INFO] Banco nao encontrado. Sera criado na inicializacao do Orchestrator.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"[MIGRATE] Conectado a: {DB_PATH}")

    # 1. Adicionar colunas faltantes em automations
    for col in ["test_mode INTEGER DEFAULT 0", "max_runtime_minutes INTEGER DEFAULT 60", "notification_channels TEXT"]:
        col_name = col.split()[0]
        try:
            cursor.execute(f"ALTER TABLE automations ADD COLUMN {col}")
            print(f"[OK] Coluna '{col_name}' adicionada em automations.")
        except sqlite3.OperationalError:
            print(f"[SKIP] Coluna '{col_name}' ja existe.")

    # 2. Adicionar coluna duration_seconds em executions (se nao existir)
    try:
        cursor.execute("ALTER TABLE executions ADD COLUMN duration_seconds REAL")
        print("[OK] Coluna 'duration_seconds' adicionada em executions.")
    except sqlite3.OperationalError:
        print("[SKIP] Coluna 'duration_seconds' ja existe.")

    # 2. Criar tabela worker_heartbeat
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worker_heartbeat (
            id INTEGER PRIMARY KEY DEFAULT 1,
            pid INTEGER,
            last_ping DATETIME DEFAULT CURRENT_TIMESTAMP,
            uptime_seconds REAL DEFAULT 0,
            tasks_completed INTEGER DEFAULT 0,
            tasks_failed INTEGER DEFAULT 0,
            active_tasks INTEGER DEFAULT 0,
            version TEXT DEFAULT '4.0.0'
        )
    """)
    print("[OK] Tabela 'worker_heartbeat' criada/verificada.")

    # 3. Criar tabela audit_log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            actor TEXT DEFAULT 'SYSTEM',
            details TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_audit_action_ts ON audit_log(action, timestamp)")
    print("[OK] Tabela 'audit_log' criada/verificada.")

    # 4. Criar indexes compostos em executions
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_exec_status_started ON executions(status, started_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_exec_auto_status ON executions(automation_id, status)")
    print("[OK] Indexes compostos criados/verificados.")

    # 5. Normalizar schedules de Python dict para JSON
    cursor.execute("SELECT id, schedule FROM automations WHERE schedule IS NOT NULL AND schedule != ''")
    rows = cursor.fetchall()
    migrated = 0
    for row_id, sched in rows:
        if sched and "'" in sched:
            try:
                import json, ast
                obj = ast.literal_eval(sched)
                new_sched = json.dumps(obj)
                cursor.execute("UPDATE automations SET schedule = ? WHERE id = ?", (new_sched, row_id))
                migrated += 1
            except Exception as e:
                print(f"[WARN] Nao foi possivel migrar schedule do id={row_id}: {e}")
    if migrated:
        print(f"[OK] {migrated} schedules migrados de Python dict para JSON.")
    else:
        print("[SKIP] Nenhum schedule precisou de migracao.")

    # 6. Preencher duration_seconds retroativamente
    cursor.execute("""
        UPDATE executions
        SET duration_seconds = ROUND((julianday(finished_at) - julianday(started_at)) * 86400, 2)
        WHERE finished_at IS NOT NULL AND duration_seconds IS NULL
    """)
    updated = cursor.rowcount
    if updated:
        print(f"[OK] {updated} execucoes tiveram 'duration_seconds' calculado retroativamente.")

    # 7. Registrar migracao no audit_log
    cursor.execute(
        "INSERT INTO audit_log (action, entity_type, actor, details) VALUES (?, ?, ?, ?)",
        ("MIGRATION_V4", "SYSTEM", "migrate_v4.py", f"Migracao executada em {datetime.now().isoformat()}")
    )

    conn.commit()
    conn.close()
    print("\n[CONCLUIDO] Migracao v4.0 finalizada com sucesso.")


if __name__ == "__main__":
    migrate()
