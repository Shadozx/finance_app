import asyncio
import pytest

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from testcontainers.postgres import PostgresContainer

from app.core import Base
from app.models import User, Category, Currency
from app.repositories import UserRepository, CategoryRepository, TransactionRepository, TransactionTemplateRepository


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:15-alpine") as postgres:
        yield postgres


@pytest.fixture
async def test_engine(postgres_container):
    postgres_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    engine = create_async_engine(postgres_url)

    async with engine.begin() as conn:
        from app.models import User, Currency, Category, Transaction, TransactionTemplate
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    async with test_engine.connect() as connection:
        trans = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        session = session_factory()
        yield session

        await session.close()

        try:
            await trans.rollback()
        except Exception:
            pass


@pytest.fixture
async def user(test_session: AsyncSession):
    user = User(
        email="testuser@test.com",
        username="testuser",
        hashed_password="hashed_password",
    )

    test_session.add(user)

    await test_session.commit()

    await test_session.refresh(user)

    return user


@pytest.fixture
async def category(
        test_session: AsyncSession,
        user: User
):
    category = Category(
        name="General",
        user_id=user.id,
        archived_at=None
    )

    test_session.add(category)

    await test_session.commit()

    await test_session.refresh(category)

    return category


@pytest.fixture
async def uah_currency(test_session: AsyncSession):
    currency = Currency(
        code="UAH",
        symbol="₴",
        name="Ukrainian Hryvnia",
        is_active=True
    )

    test_session.add(currency)

    await test_session.commit()

    await test_session.refresh(currency)

    return currency


@pytest.fixture
async def usd_currency(test_session):
    currency = Currency(
        code="USD",
        symbol="$",
        name="US Dollar",
        is_active=True
    )

    test_session.add(currency)

    await test_session.commit()

    await test_session.refresh(currency)

    return currency


@pytest.fixture
def category_repository(test_session: AsyncSession):
    return CategoryRepository(test_session)


@pytest.fixture
def transaction_repository(
        test_session: AsyncSession,
):
    return TransactionRepository(test_session)


@pytest.fixture
def transaction_template_repository(
        test_session: AsyncSession
):
    return TransactionTemplateRepository(test_session)


@pytest.fixture
def user_repository(test_session):
    return UserRepository(test_session)
