# pylint: disable=invalid-name
"""compress_execution_logs

Altera Execution.logs para usar CompressedText (zlib+base64) no ORM.
No SQLite a coluna continua sendo Text — a compressão ocorre na camada Python.
Dados legados são lidos corretamente pelo fallback em CompressedText.process_result_value.

Revision ID: 20260620_02
Revises: 20260620_01
Create Date: 2026-06-20 00:00:00.000000
"""

revision = "20260620_02"
down_revision = "20260620_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sem alteração DDL: CompressedText é transparente para o SQLite (impl = Text).
    # Novos registros serão escritos comprimidos; legados são lidos pelo fallback.
    pass


def downgrade() -> None:
    # Sem alteração DDL na descida — dados já comprimidos precisam de migração
    # manual de dados se o downgrade for permanente.
    pass
