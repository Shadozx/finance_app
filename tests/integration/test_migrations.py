import enum
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Connection, inspect, make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command
from app.core import Base
from app.models import CategoryType, TransactionKind, TransactionType

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
MIGRATIONS_DATABASE = "migrations_test"
HEAD_REVISION = "head"
BASE_REVISION = "base"
VERSION_TABLE = "alembic_version"
CURRENCY_CODE = "UAH"

SEED_CURRENCIES_REVISION = "e916b5746c68"
TRANSACTION_KIND_REVISION = "c75ba8ee8757"
TRANSFER_KIND_REVISION = "1bb92b3f825f"
SETTLED_AMOUNT_REVISION = "ec935c6ee93e"
TIMESTAMPS_REVISION = "fb292ab1bb42"
PASSWORD_CHANGED_AT_REVISION = "d9da74d03578"
CATEGORY_TYPE_REVISION = "a42e8b91c630"


def before(revision: str) -> str:
    """The revision right before the given one, in Alembic's relative syntax."""

    return f"{revision}-1"


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


async def insert(engine: AsyncEngine, statement: str, **parameters):
    """Raw SQL: at an old revision the models no longer describe the schema."""

    async with engine.begin() as connection:
        result = await connection.execute(text(statement), parameters)

        return result.scalar_one() if result.returns_rows else None


async def fetch_row(engine: AsyncEngine, statement: str):
    async with engine.connect() as connection:
        result = await connection.execute(text(statement))

        return result.one()


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

    @pytest.mark.parametrize(
        "type_name, declared_enum",
        [
            ("categorytype", CategoryType),
            ("transactiontype", TransactionType),
            ("transactionkind", TransactionKind),
        ],
    )
    async def test_enum_labels_and_their_order_match_models(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
        type_name: str,
        declared_enum: type[enum.Enum],
    ):
        """`alembic check` compares tables and columns, never enum labels.

        The order is part of the type: it decides how ORDER BY sorts such a column.
        """
        expected_labels = [member.name for member in declared_enum]
        await upgrade(migrations_engine, alembic_config)

        row = await fetch_row(
            migrations_engine,
            "SELECT array_agg(enumlabel::text ORDER BY enumsortorder) AS labels"
            " FROM pg_enum JOIN pg_type ON pg_type.oid = pg_enum.enumtypid"
            f" WHERE pg_type.typname = '{type_name}'",
        )

        assert row.labels == expected_labels


class TestDataMigrations:
    """Backfills run on rows that already exist, so an empty database proves nothing:
    each test seeds the old shape, applies one step, and reads what the step wrote."""

    async def insert_user(self, engine: AsyncEngine, email: str = "user@test.com") -> int:
        return await insert(
            engine,
            "INSERT INTO users (username, email, hashed_password, created_at)"
            " VALUES (:username, :email, :hashed_password, now()) RETURNING id",
            username=email.split("@")[0],
            email=email,
            hashed_password="hashed_password",
        )

    async def insert_category(self, engine: AsyncEngine, user_id: int) -> int:
        return await insert(
            engine,
            "INSERT INTO categories (name, user_id, archived_at, created_at)"
            " VALUES (:name, :user_id, NULL, now()) RETURNING id",
            name="General",
            user_id=user_id,
        )

    async def insert_account(self, engine: AsyncEngine, user_id: int) -> int:
        return await insert(
            engine,
            "INSERT INTO accounts (name, currency_code, user_id, archived_at, created_at)"
            " VALUES (:name, :currency_code, :user_id, NULL, now()) RETURNING id",
            name="Card",
            currency_code=CURRENCY_CODE,
            user_id=user_id,
        )

    async def insert_user_before_category_type(
        self, engine: AsyncEngine, email: str = "category_owner@test.com"
    ) -> int:
        return await insert(
            engine,
            "INSERT INTO users (username, email, hashed_password, created_at, password_changed_at)"
            " VALUES (:username, :email, :password, now(), now()) RETURNING id",
            username=email.split("@")[0],
            email=email,
            password="hashed_password",
        )

    async def insert_category_before_category_type(
        self, engine: AsyncEngine, user_id: int, name: str = "General"
    ) -> int:
        return await insert(
            engine,
            "INSERT INTO categories (name, user_id, created_at, updated_at)"
            " VALUES (:name, :user_id, now(), now()) RETURNING id",
            name=name,
            user_id=user_id,
        )

    async def insert_account_before_category_type(self, engine: AsyncEngine, user_id: int) -> int:
        return await insert(
            engine,
            "INSERT INTO accounts (name, currency_code, user_id, created_at, updated_at)"
            " VALUES (:name, :currency_code, :user_id, now(), now()) RETURNING id",
            name="Card",
            currency_code=CURRENCY_CODE,
            user_id=user_id,
        )

    async def insert_transaction(
        self,
        engine: AsyncEngine,
        *,
        user_id: int,
        category_id: int,
        account_id: int,
        transaction_type: str,
        kind: str,
        source: str,
    ) -> None:
        amount = Decimal("100.00")
        transaction_date = date(2026, 1, 1)
        transaction_id = await insert(
            engine,
            "INSERT INTO transactions"
            " (type, kind, amount, settled_amount, currency_code, settled_currency_code,"
            " user_id, category_id, account_id, date, created_at, updated_at)"
            " VALUES (:type, :kind, :amount, :amount, :currency_code, :currency_code,"
            " :user_id, :category_id, :account_id, :date, now(), now()) RETURNING id",
            type=transaction_type,
            kind=kind,
            amount=amount,
            currency_code=CURRENCY_CODE,
            user_id=user_id,
            category_id=category_id if source == "direct" else None,
            account_id=account_id,
            date=transaction_date,
        )
        if source == "split":
            await insert(
                engine,
                "INSERT INTO transaction_splits"
                " (transaction_id, category_id, amount, settled_amount, created_at, updated_at)"
                " VALUES (:transaction_id, :category_id, :amount, :amount, now(), now())",
                transaction_id=transaction_id,
                category_id=category_id,
                amount=amount,
            )

    async def test_seed_currencies_inserts_the_reference_currencies(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        expected_codes = ["EUR", "GBP", "PLN", "UAH", "USD"]

        await upgrade(migrations_engine, alembic_config, before(SEED_CURRENCIES_REVISION))
        await upgrade(migrations_engine, alembic_config, SEED_CURRENCIES_REVISION)

        row = await fetch_row(
            migrations_engine,
            "SELECT array_agg(code ORDER BY code) AS codes FROM currencies",
        )

        assert row.codes == expected_codes

    async def test_transaction_kind_backfills_existing_rows_as_regular(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        expected_kind = "REGULAR"

        await upgrade(migrations_engine, alembic_config, before(TRANSACTION_KIND_REVISION))

        user_id = await self.insert_user(migrations_engine)
        category_id = await self.insert_category(migrations_engine, user_id)

        await insert(
            migrations_engine,
            "INSERT INTO transactions (type, amount, currency_code, user_id, category_id, date)"
            " VALUES ('EXPENSE', :amount, :currency_code, :user_id, :category_id, :date)",
            amount=Decimal("100.00"),
            currency_code=CURRENCY_CODE,
            user_id=user_id,
            category_id=category_id,
            date=date(2026, 1, 1),
        )

        await upgrade(migrations_engine, alembic_config, TRANSACTION_KIND_REVISION)

        row = await fetch_row(migrations_engine, "SELECT kind::text AS kind FROM transactions")

        assert row.kind == expected_kind

    async def test_settled_amount_backfills_from_the_original_amount(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        await upgrade(migrations_engine, alembic_config, before(SETTLED_AMOUNT_REVISION))

        user_id = await self.insert_user(migrations_engine)
        category_id = await self.insert_category(migrations_engine, user_id)
        account_id = await self.insert_account(migrations_engine, user_id)

        await insert(
            migrations_engine,
            "INSERT INTO transactions"
            " (type, kind, amount, currency_code, user_id, category_id, account_id, date)"
            " VALUES ('EXPENSE', 'REGULAR', :amount, :currency_code, :user_id, :category_id,"
            " :account_id, :date)",
            amount=Decimal("100.00"),
            currency_code=CURRENCY_CODE,
            user_id=user_id,
            category_id=category_id,
            account_id=account_id,
            date=date(2026, 1, 1),
        )

        await upgrade(migrations_engine, alembic_config, SETTLED_AMOUNT_REVISION)

        row = await fetch_row(
            migrations_engine,
            "SELECT settled_amount = amount"
            " AND settled_currency_code = currency_code AS copied FROM transactions",
        )

        assert row.copied is True

    async def test_timestamps_backfill_updated_at_from_created_at(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        await upgrade(migrations_engine, alembic_config, before(TIMESTAMPS_REVISION))

        user_id = await self.insert_user(migrations_engine)

        await self.insert_category(migrations_engine, user_id)

        await upgrade(migrations_engine, alembic_config, TIMESTAMPS_REVISION)

        row = await fetch_row(
            migrations_engine,
            "SELECT updated_at = created_at AS derived FROM categories",
        )

        assert row.derived is True

    async def test_timestamps_stamp_rows_that_have_nothing_to_derive_them_from(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        await upgrade(migrations_engine, alembic_config, before(TIMESTAMPS_REVISION))

        user_id = await self.insert_user(migrations_engine)
        category_id = await self.insert_category(migrations_engine, user_id)
        account_id = await self.insert_account(migrations_engine, user_id)

        await insert(
            migrations_engine,
            "INSERT INTO transactions"
            " (type, kind, amount, settled_amount, currency_code, settled_currency_code,"
            " user_id, category_id, account_id, date)"
            " VALUES ('EXPENSE', 'REGULAR', :amount, :amount, :currency_code, :currency_code,"
            " :user_id, :category_id, :account_id, :date)",
            amount=Decimal("100.00"),
            currency_code=CURRENCY_CODE,
            user_id=user_id,
            category_id=category_id,
            account_id=account_id,
            date=date(2026, 1, 1),
        )

        await insert(
            migrations_engine,
            "INSERT INTO budgets"
            " (name, amount, currency_code, user_id, category_id, start_date, end_date)"
            " VALUES (:name, :amount, :currency_code, :user_id, :category_id, :start, :end)",
            name="Food",
            amount=Decimal("5000.00"),
            currency_code=CURRENCY_CODE,
            user_id=user_id,
            category_id=category_id,
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
        )

        await upgrade(migrations_engine, alembic_config, TIMESTAMPS_REVISION)

        row = await fetch_row(
            migrations_engine,
            "SELECT (SELECT count(*) FROM transactions WHERE created_at IS NULL"
            " OR updated_at IS NULL)"
            " + (SELECT count(*) FROM budgets WHERE created_at IS NULL OR updated_at IS NULL)"
            " AS unstamped",
        )

        assert row.unstamped == 0

    async def test_transfer_revision_adds_the_transfer_kind_label(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        expected_labels = ["ADJUSTMENT", "REGULAR", "TRANSFER"]

        await upgrade(migrations_engine, alembic_config, TRANSFER_KIND_REVISION)

        row = await fetch_row(
            migrations_engine,
            "SELECT array_agg(enumlabel::text ORDER BY enumlabel) AS labels"
            " FROM pg_enum JOIN pg_type ON pg_type.oid = pg_enum.enumtypid"
            " WHERE pg_type.typname = 'transactionkind'",
        )

        assert row.labels == expected_labels

    async def test_password_changed_at_backfills_from_created_at(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        await upgrade(migrations_engine, alembic_config, before(PASSWORD_CHANGED_AT_REVISION))

        await self.insert_user(migrations_engine)

        await upgrade(migrations_engine, alembic_config, PASSWORD_CHANGED_AT_REVISION)

        row = await fetch_row(
            migrations_engine,
            "SELECT password_changed_at = created_at AS derived FROM users",
        )

        assert row.derived is True

    @pytest.mark.parametrize(
        "direct_types, split_types, expected_type",
        [
            pytest.param([], [], "ANY", id="no-history"),
            pytest.param(["EXPENSE"], [], "EXPENSE", id="expense"),
            pytest.param(["INCOME"], [], "INCOME", id="income"),
            pytest.param(["EXPENSE", "INCOME"], [], "ANY", id="mixed-direct"),
            pytest.param([], ["EXPENSE"], "EXPENSE", id="split-expense"),
            pytest.param([], ["INCOME"], "INCOME", id="split-income"),
            pytest.param(["EXPENSE"], ["INCOME"], "ANY", id="mixed-sources"),
        ],
    )
    async def test_category_type_backfills_from_regular_history(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
        direct_types: list[str],
        split_types: list[str],
        expected_type: str,
    ):
        await upgrade(migrations_engine, alembic_config, before(CATEGORY_TYPE_REVISION))

        user_id = await self.insert_user_before_category_type(migrations_engine)
        category_id = await self.insert_category_before_category_type(migrations_engine, user_id)
        account_id = await self.insert_account_before_category_type(migrations_engine, user_id)

        for transaction_type in direct_types:
            await self.insert_transaction(
                migrations_engine,
                user_id=user_id,
                category_id=category_id,
                account_id=account_id,
                transaction_type=transaction_type,
                kind="REGULAR",
                source="direct",
            )
        for transaction_type in split_types:
            await self.insert_transaction(
                migrations_engine,
                user_id=user_id,
                category_id=category_id,
                account_id=account_id,
                transaction_type=transaction_type,
                kind="REGULAR",
                source="split",
            )

        await upgrade(migrations_engine, alembic_config, CATEGORY_TYPE_REVISION)

        row = await fetch_row(migrations_engine, "SELECT type::text AS type FROM categories")

        assert row.type == expected_type

    @pytest.mark.parametrize("kind", ["ADJUSTMENT", "TRANSFER"])
    @pytest.mark.parametrize("source", ["direct", "split"])
    async def test_category_type_ignores_service_operations(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
        kind: str,
        source: str,
    ):
        expected_type = "ANY"
        transaction_type = "EXPENSE"

        await upgrade(migrations_engine, alembic_config, before(CATEGORY_TYPE_REVISION))

        user_id = await self.insert_user_before_category_type(migrations_engine)
        category_id = await self.insert_category_before_category_type(migrations_engine, user_id)
        account_id = await self.insert_account_before_category_type(migrations_engine, user_id)
        await self.insert_transaction(
            migrations_engine,
            user_id=user_id,
            category_id=category_id,
            account_id=account_id,
            transaction_type=transaction_type,
            kind=kind,
            source=source,
        )

        await upgrade(migrations_engine, alembic_config, CATEGORY_TYPE_REVISION)

        row = await fetch_row(migrations_engine, "SELECT type::text AS type FROM categories")

        assert row.type == expected_type

    @pytest.mark.parametrize("source", ["direct", "split"])
    async def test_category_type_ignores_templates(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
        source: str,
    ):
        expected_type = "ANY"
        amount = Decimal("100.00")

        await upgrade(migrations_engine, alembic_config, before(CATEGORY_TYPE_REVISION))

        user_id = await self.insert_user_before_category_type(migrations_engine)
        category_id = await self.insert_category_before_category_type(migrations_engine, user_id)
        template_id = await insert(
            migrations_engine,
            "INSERT INTO transaction_templates"
            " (name, type, amount, currency_code, user_id, category_id, created_at, updated_at)"
            " VALUES (:name, 'EXPENSE', :amount, :currency_code, :user_id, :category_id,"
            " now(), now()) RETURNING id",
            name="Regular purchase",
            amount=amount,
            currency_code=CURRENCY_CODE,
            user_id=user_id,
            category_id=category_id if source == "direct" else None,
        )
        if source == "split":
            await insert(
                migrations_engine,
                "INSERT INTO transaction_template_splits"
                " (transaction_template_id, category_id, amount, created_at, updated_at)"
                " VALUES (:template_id, :category_id, :amount, now(), now())",
                template_id=template_id,
                category_id=category_id,
                amount=amount,
            )

        await upgrade(migrations_engine, alembic_config, CATEGORY_TYPE_REVISION)

        row = await fetch_row(migrations_engine, "SELECT type::text AS type FROM categories")

        assert row.type == expected_type

    @pytest.mark.parametrize("source", ["direct", "split"])
    async def test_category_type_ignores_other_users_history(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
        source: str,
    ):
        expected_type = "ANY"
        transaction_type = "EXPENSE"
        other_email = "other_user@test.com"

        await upgrade(migrations_engine, alembic_config, before(CATEGORY_TYPE_REVISION))

        owner_id = await self.insert_user_before_category_type(migrations_engine)
        category_id = await self.insert_category_before_category_type(migrations_engine, owner_id)
        other_user_id = await self.insert_user_before_category_type(
            migrations_engine, email=other_email
        )
        account_id = await self.insert_account_before_category_type(
            migrations_engine, other_user_id
        )
        await self.insert_transaction(
            migrations_engine,
            user_id=other_user_id,
            category_id=category_id,
            account_id=account_id,
            transaction_type=transaction_type,
            kind="REGULAR",
            source=source,
        )

        await upgrade(migrations_engine, alembic_config, CATEGORY_TYPE_REVISION)

        row = await fetch_row(migrations_engine, "SELECT type::text AS type FROM categories")

        assert row.type == expected_type

    async def test_category_type_restores_each_category_from_history_after_downgrade(
        self,
        migrations_engine: AsyncEngine,
        alembic_config: Config,
    ):
        await upgrade(migrations_engine, alembic_config, before(CATEGORY_TYPE_REVISION))

        user_id = await self.insert_user_before_category_type(migrations_engine)
        expense_category_id = await self.insert_category_before_category_type(
            migrations_engine, user_id
        )
        income_category_id = await self.insert_category_before_category_type(
            migrations_engine, user_id, name="Salary"
        )
        account_id = await self.insert_account_before_category_type(migrations_engine, user_id)
        await self.insert_transaction(
            migrations_engine,
            user_id=user_id,
            category_id=expense_category_id,
            account_id=account_id,
            transaction_type="EXPENSE",
            kind="REGULAR",
            source="direct",
        )
        await self.insert_transaction(
            migrations_engine,
            user_id=user_id,
            category_id=income_category_id,
            account_id=account_id,
            transaction_type="INCOME",
            kind="REGULAR",
            source="split",
        )
        expected_ids = [expense_category_id, income_category_id]
        expected_types = ["EXPENSE", "INCOME"]
        category_query = (
            "SELECT array_agg(id ORDER BY id) AS ids,"
            " array_agg(type::text ORDER BY id) AS types FROM categories"
        )

        await upgrade(migrations_engine, alembic_config, CATEGORY_TYPE_REVISION)
        first_result = await fetch_row(migrations_engine, category_query)

        assert first_result.ids == expected_ids
        assert first_result.types == expected_types

        await downgrade(migrations_engine, alembic_config, before(CATEGORY_TYPE_REVISION))
        await upgrade(migrations_engine, alembic_config, CATEGORY_TYPE_REVISION)
        repeated_result = await fetch_row(migrations_engine, category_query)

        assert repeated_result.ids == expected_ids
        assert repeated_result.types == expected_types
