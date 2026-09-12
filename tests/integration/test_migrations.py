from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Connection, inspect, make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command
from app.core import Base

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
MIGRATIONS_DATABASE = "migrations_test"
HEAD_REVISION = "head"
BASE_REVISION = "base"
VERSION_TABLE = "alembic_version"


def _upgrade(connection: Connection, config: Config, revision: str) -> None:
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


def _downgrade(connection: Connection, config: Config, revision: str) -> None:
    config.attributes["connection"] = connection
    command.downgrade(config, revision)


def _check(connection: Connection, config: Config) -> None:
    config.attributes["connection"] = connection
    command.check(config)


def _table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


async def upgrade(engine: AsyncEngine, config: Config, revision: str = HEAD_REVISION) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(_upgrade, config, revision)
        await connection.commit()


async def downgrade(engine: AsyncEngine, config: Config, revision: str = BASE_REVISION) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(_downgrade, config, revision)
        await connection.commit()


async def check(engine: AsyncEngine, config: Config) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(_check, config)


async def table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(_table_names)


@pytest.fixture
def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


@pytest.fixture
async def migrations_engine(postgres_container: PostgresContainer) -> AsyncIterator[AsyncEngine]:
    container_url = make_url(postgres_container.get_connection_url().replace("psycopg2", "asyncpg"))

    admin_engine = create_async_engine(container_url, isolation_level="AUTOCOMMIT")

    async with admin_engine.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATIONS_DATABASE}"'))
        await connection.execute(text(f'CREATE DATABASE "{MIGRATIONS_DATABASE}"'))

    await admin_engine.dispose()

    engine = create_async_engine(container_url.set(database=MIGRATIONS_DATABASE))

    yield engine

    await engine.dispose()


class TestMigrations:
    async def test_upgrade_head_creates_every_table_declared_by_models(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        await upgrade(migrations_engine, alembic_config)

        assert set(Base.metadata.tables) <= await table_names(migrations_engine)

    async def test_upgrade_head_leaves_no_difference_from_models(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        await upgrade(migrations_engine, alembic_config)

        await check(migrations_engine, alembic_config)

    async def test_downgrade_base_leaves_only_the_version_table(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        await upgrade(migrations_engine, alembic_config)
        await downgrade(migrations_engine, alembic_config)

        assert await table_names(migrations_engine) == {VERSION_TABLE}

    async def test_upgrade_head_runs_again_after_downgrade_base(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        await upgrade(migrations_engine, alembic_config)
        await downgrade(migrations_engine, alembic_config)
        await upgrade(migrations_engine, alembic_config)

        assert set(Base.metadata.tables) <= await table_names(migrations_engine)
