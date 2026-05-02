from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import os
import sys
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 현재 경로를 파이썬 경로에 추가하여 models를 임포트할 수 있게 함
sys.path.append(os.getcwd())

from models import Base
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


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
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # 환경 변수에서 DATABASE_URL을 가져오거나 기본값을 사용함
    db_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    
    # URL의 드라이버가 psycopg+psycopg인 경우 비동기 드라이버일 수 있으므로 동기 드라이버 postgresql로 치환 (alembic용)
    if db_url and "psycopg+psycopg" in db_url:
        db_url = db_url.replace("psycopg+psycopg", "postgresql")
    elif db_url and "postgresql+psycopg" in db_url:
        db_url = db_url.replace("postgresql+psycopg", "postgresql")

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=db_url  # 환경 변수에서 가져온 URL 주입
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
