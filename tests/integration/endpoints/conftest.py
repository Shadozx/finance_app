from collections.abc import AsyncGenerator

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.api.dependencies import get_session
from app.models import Currency

from tests.integration.endpoints.helpers import register_payload, category_payload, create_category, archive_category, create_account, account_payload
from tests.integration.endpoints.types import AuthenticatedUser, CategoryData, CurrencyData, UserData, AccountData


@pytest.fixture
async def client(test_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session():
        yield test_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def disable_rate_limiter():
    previous_state = app.state.limiter.enabled

    app.state.limiter.enabled = False

    yield

    app.state.limiter.enabled = previous_state


@pytest.fixture
async def registered_user(
        client: AsyncClient
) -> UserData:
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
async def authenticated_user(
        client: AsyncClient,
        registered_user: UserData
) -> AuthenticatedUser:
    response = await client.post("/api/v1/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })

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

    login_response = await client.post("/api/v1/auth/login", json={
        "email": payload["email"],
        "password": payload["password"],
    })
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
        client,
        category_payload(),
        authenticated_user["headers"]
    )


@pytest.fixture
async def archived_category(
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
) -> CategoryData:
    category = await create_category(
        client,
        category_payload(),
        authenticated_user["headers"]
    )

    await archive_category(
        client,
        category["id"],
        authenticated_user["headers"]
    )

    return category


@pytest.fixture
async def active_currency(
        test_session: AsyncSession
) -> CurrencyData:
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
async def inactive_currency(
        test_session: AsyncSession
) -> CurrencyData:
    currency = Currency(
        code="OLD",
        name="Old Currency",
        symbol="¤",
        is_active=False
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