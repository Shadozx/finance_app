from httpx import AsyncClient
from fastapi import status

from tests.integration.endpoints.types import CategoryData, TransactionTemplateData, TransactionData, AccountData, TransferData


def register_payload(
        email: str = "user@test.com",
        username: str = "testuser",
        password: str = "Password123",
) -> dict[str, str]:
    return {
        "email": email,
        "username": username,
        "password": password,
    }


def category_payload(name: str = "Food") -> dict[str, str]:
    return {"name": name}


async def create_category(
        client: AsyncClient,
        payload: dict[str, str],
        headers: dict[str, str],
) -> CategoryData:
    response = await client.post(
        "/api/v1/categories",
        json=payload,
        headers=headers,
    )

    assert response.status_code == status.HTTP_201_CREATED

    return response.json()


async def archive_category(
        client: AsyncClient,
        category_id: int,
        headers: dict[str, str],
) -> None:
    response = await client.delete(
        f"/api/v1/categories/{category_id}",
        headers=headers,
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT


def transaction_template_payload(
        name: str = "Lunch template",
        amount: str = "150.00",
        template_type: str = "EXPENSE",
        currency_code: str = "USD",
        category_id: int | None = None,
        description: str | None = None
) -> dict[str, object]:
    return {
        "name": name,
        "amount": amount,
        "type": template_type,
        "currency_code": currency_code,
        "category_id": category_id,
        "description": description,
    }


async def create_transaction_template(
        client: AsyncClient,
        payload: dict[str, object],
        headers: dict[str, str],
) -> TransactionTemplateData:
    response = await client.post(
        "/api/v1/transactions/templates",
        json=payload,
        headers=headers,
    )

    assert response.status_code == status.HTTP_201_CREATED

    return response.json()


def transaction_payload(
        date: str = "2026-01-01",
        amount: str = "150.00",
        transaction_type: str = "EXPENSE",
        currency_code: str = "USD",
        settled_amount: str | None = None,
        account_id: int | None = None,
        category_id: int | None = None,
        description: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "date": date,
        "amount": amount,
        "type": transaction_type,
        "currency_code": currency_code,
        "category_id": category_id,
        "description": description,
        "account_id": account_id,
    }

    if settled_amount is not None:
        payload["settled_amount"] = settled_amount

    return payload


async def create_transaction(
        client: AsyncClient,
        payload: dict[str, object],
        headers: dict[str, str],
) -> TransactionData:
    response = await client.post(
        "/api/v1/transactions",
        json=payload,
        headers=headers,
    )

    assert response.status_code == status.HTTP_201_CREATED

    return response.json()

def account_payload(
        name: str = "Monobank",
        currency_code: str = "USD",
) -> dict[str, str]:
    return {"name": name, "currency_code": currency_code}


async def create_account(client, payload, headers) -> AccountData:
    response = await client.post("/api/v1/accounts", json=payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()

async def archive_account(
        client: AsyncClient,
        account_id: int,
        headers: dict[str, str],
) -> None:
    response = await client.delete(
        f"/api/v1/accounts/{account_id}",
        headers=headers,
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT


def transfer_payload(
        from_account_id: int,
        to_account_id: int,
        from_amount: str = "100.00",
        to_amount: str = "100.00",
        date: str = "2026-01-01",
        description: str | None = None,
) -> dict[str, object]:
    return {
        "from_account_id": from_account_id,
        "to_account_id": to_account_id,
        "from_amount": from_amount,
        "to_amount": to_amount,
        "date": date,
        "description": description,
    }


async def create_transfer(
        client: AsyncClient,
        payload: dict[str, object],
        headers: dict[str, str],
) -> TransferData:
    response = await client.post(
        "/api/v1/transfers",
        json=payload,
        headers=headers,
    )

    assert response.status_code == status.HTTP_201_CREATED

    return response.json()