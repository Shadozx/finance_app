from httpx import AsyncClient
from fastapi import status

from tests.integration.endpoints.types import CategoryData, TransactionTemplateData, TransactionData


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
        category_id: int | None = None,
        description: str | None = None,
) -> dict[str, object]:
    return {
        "date": date,
        "amount": amount,
        "type": transaction_type,
        "currency_code": currency_code,
        "category_id": category_id,
        "description": description,
    }


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
