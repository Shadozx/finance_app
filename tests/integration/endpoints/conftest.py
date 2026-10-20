from collections.abc import AsyncGenerator

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_session
from app.core import Base
from app.main import app
from app.models import Currency
from tests.integration.endpoints.helpers import (
    CLEANUP_LOCK_TIMEOUT_SECONDS,
    account_payload,
    archive_account,
    archive_category,
    category_payload,
    create_account,
    create_category,
    create_transfer,
    register_payload,
    transfer_payload,
)
from tests.integration.endpoints.types import (
    AccountData,
    AuthenticatedUser,
    CategoryData,
    CurrencyData,
    TransferData,
    UserData,
)


@pytest.fixture
async def client(test_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session():
        yield test_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def independent_session_factory(
    request: pytest.FixtureRequest,
    test_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Sessions on their own connections, committing for real, for concurrency tests.

    Unlike test_session, nothing is rolled back, so all tables are truncated after the test.
    Never combine it with client or test_session: their data sits in an uncommitted
    transaction that these sessions cannot see and whose locks would block the cleanup.
    """
    if "test_session" in request.fixturenames:
        pytest.fail("independent_session_factory cannot be combined with client or test_session")

    yield async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    preparer = test_engine.dialect.identifier_preparer
    table_names = ", ".join(preparer.format_table(table) for table in Base.metadata.sorted_tables)

    # The lock timeout is local to this transaction: a session left open by a cancelled
    # request fails the cleanup loudly instead of hanging it
    async with test_engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('lock_timeout', :value, true)"),
            {"value": f"{CLEANUP_LOCK_TIMEOUT_SECONDS}s"},
        )
        await connection.execute(text(f"TRUNCATE {table_names} CASCADE"))


@pytest.fixture
async def independent_client(
    independent_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """Client whose every request gets its own session, as in production."""

    async def override_get_session():
        async with independent_session_factory() as session:
            yield session

    previous_override = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    if previous_override is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = previous_override


@pytest.fixture(autouse=True)
def disable_rate_limiter():
    previous_state = app.state.limiter.enabled

    app.state.limiter.enabled = False

    yield

    app.state.limiter.enabled = previous_state


@pytest.fixture
async def registered_user(client: AsyncClient) -> UserData:
    payload = register_payload()

    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == status.HTTP_201_CREATED

    user_data: UserData = {
        "id": response.json()["id"],
        "email": payload["email"],
        "username": payload["username"],
        "password": payload["password"],
    }

    return user_data


@pytest.fixture
async def authenticated_user(client: AsyncClient, registered_user: UserData) -> AuthenticatedUser:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )

    assert response.status_code == status.HTTP_200_OK

    token = response.json()["access_token"]

    return {
        "user": registered_user,
        "headers": {
            "Authorization": f"Bearer {token}",
        },
    }


@pytest.fixture
async def other_authenticated_user(
    client: AsyncClient,
) -> AuthenticatedUser:
    payload = register_payload(
        email="otheruser@test.com",
        username="otheruser",
        password="OtherUserPassword123",
    )

    register_response = await client.post("/api/v1/auth/register", json=payload)
    assert register_response.status_code == status.HTTP_201_CREATED

    user_data: UserData = {
        "id": register_response.json()["id"],
        "email": payload["email"],
        "username": payload["username"],
        "password": payload["password"],
    }

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )
    assert login_response.status_code == status.HTTP_200_OK

    return {
        "user": user_data,
        "headers": {
            "Authorization": f"Bearer {login_response.json()['access_token']}",
        },
    }


@pytest.fixture
async def created_category(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
) -> CategoryData:
    return await create_category(
        client, category_payload(name="Active category"), authenticated_user["headers"]
    )


@pytest.fixture
async def archived_category(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
) -> CategoryData:
    category = await create_category(
        client, category_payload(name="Archived category"), authenticated_user["headers"]
    )

    await archive_category(client, category["id"], authenticated_user["headers"])

    return category


@pytest.fixture
async def active_currency(test_session: AsyncSession) -> CurrencyData:
    currency = Currency(
        code="USD",
        name="US Dollar",
        symbol="$",
        is_active=True,
    )

    test_session.add(currency)
    await test_session.commit()
    await test_session.refresh(currency)

    return {
        "code": currency.code,
        "name": currency.name,
        "symbol": currency.symbol,
        "is_active": currency.is_active,
    }


@pytest.fixture
async def inactive_currency(test_session: AsyncSession) -> CurrencyData:
    currency = Currency(code="OLD", name="Old Currency", symbol="¤", is_active=False)

    test_session.add(currency)
    await test_session.commit()
    await test_session.refresh(currency)

    return {
        "code": currency.code,
        "name": currency.name,
        "symbol": currency.symbol,
        "is_active": currency.is_active,
    }


@pytest.fixture
async def created_account(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
    active_currency: CurrencyData,
) -> AccountData:
    return await create_account(
        client,
        account_payload(currency_code=active_currency["code"]),
        authenticated_user["headers"],
    )


@pytest.fixture
async def second_currency(
    test_session: AsyncSession,
) -> CurrencyData:
    currency = Currency(
        code="UAH",
        name="Ukrainian Hryvnia",
        symbol="\u20b4",
        is_active=True,
    )

    test_session.add(currency)
    await test_session.commit()
    await test_session.refresh(currency)

    return {
        "code": currency.code,
        "name": currency.name,
        "symbol": currency.symbol,
        "is_active": currency.is_active,
    }


@pytest.fixture
async def uah_account(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
    second_currency: CurrencyData,
) -> AccountData:
    """Second account in another currency — the far side of a transfer."""
    return await create_account(
        client,
        account_payload(name="Cash", currency_code=second_currency["code"]),
        authenticated_user["headers"],
    )


@pytest.fixture
async def archived_account(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
    active_currency: CurrencyData,
) -> AccountData:
    account = await create_account(
        client,
        account_payload(name="Closed Card", currency_code=active_currency["code"]),
        authenticated_user["headers"],
    )

    await archive_account(client, account["id"], authenticated_user["headers"])

    return account


@pytest.fixture
async def created_transfer(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
    created_account: AccountData,
    uah_account: AccountData,
) -> TransferData:
    """Cross-currency transfer: 24 USD out, 1000 UAH in — two rows in the registry."""
    return await create_transfer(
        client,
        transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=uah_account["id"],
            from_amount="24.00",
            to_amount="1000.00",
        ),
        authenticated_user["headers"],
    )
