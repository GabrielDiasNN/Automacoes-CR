import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 1. Configurar sys.path para importar o backend do Orchestrator
current_dir = os.path.dirname(os.path.abspath(__file__))
orchestrator_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(orchestrator_dir)
sys.path.insert(0, orchestrator_dir)

# 2. Carregar variáveis de ambiente do arquivo .env
from dotenv import load_dotenv
dotenv_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path)

# Tenta primeiro a URL definida programaticamente na configuração do Alembic
db_url = context.config.get_main_option("sqlalchemy.url")

# Se for a URL padrão do .ini (placeholder) ou se não estiver definida, resolve via ambiente
if not db_url or db_url == "sqlite:///orchestrator.db":
    db_path = os.environ.get("ORCHESTRATOR_DB_PATH") or os.path.join(orchestrator_dir, "automacoes.db")
    if db_path != ":memory:" and not os.path.isabs(db_path):
        db_path = os.path.abspath(os.path.join(project_root, db_path))
    db_url = f"sqlite:///{db_path}"

# 3. Importar os modelos SQLAlchemy do Hub para suporte ao autogenerate
from app.database import Base
import app.models  # noqa: F401 (força o carregamento dos modelos)

target_metadata = Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Sobrescreve a url do banco no config com a do .env
config.set_main_option("sqlalchemy.url", db_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Crucial para compatibilidade com ALTER TABLE do SQLite
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Crucial para compatibilidade com ALTER TABLE do SQLite
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
