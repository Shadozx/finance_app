import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from decimal import Decimal
from typing import Any, TypeVar

from fastapi import status
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import verify_token
from app.core.error_codes import ErrorCode, FieldErrorCode
from app.models import CategoryType
from app.schemas.validators import MAX_AMOUNT, MAX_PASSWORD_LENGTH
from tests.integration.endpoints.types import (
    AccountData,
    CategoryData,
    TransactionData,
    TransactionTemplateData,
    TransferData,
)

T = TypeVar("T")
U = TypeVar("U")

# Upper bound for every wait in a concurrency test, so a deadlock fails instead of hanging
CONCURRENCY_TIMEOUT_SECONDS = 10

# How long the cleanup TRUNCATE waits for a lock held by a leftover transaction
CLEANUP_LOCK_TIMEOUT_SECONDS = 5

# Pause between two pg_stat_activity polls while waiting for lock waiters to queue
LOCK_POLL_INTERVAL_SECONDS = 0.05

# pg_stat_activity wait events of a transaction blocked on a row lock. The first waiter
# queues on the lock holder's transaction id (transactionid); every further waiter queues
# on the row itself (tuple). Table-level waits (relation) are deliberately excluded.
ROW_LOCK_WAIT_EVENTS = ["transactionid", "tuple"]

# Smallest step a NUMERIC(15, 2) money column can store
CENT = Decimal("0.01")

MAX_AMOUNT_VALUE = str(MAX_AMOUNT)
OVER_MAX_AMOUNT_VALUE = str(MAX_AMOUNT + CENT)
MIN_BALANCE_VALUE = str(-MAX_AMOUNT)
UNDER_MIN_BALANCE_VALUE = str(-MAX_AMOUNT - CENT)

# Passes every strength rule, so only the length can reject it
OVER_MAX_PASSWORD = ("a1" * MAX_PASSWORD_LENGTH)[: MAX_PASSWORD_LENGTH + 1]


def session_id_from_headers(headers: dict[str, str]) -> uuid.UUID:
    token = headers["Authorization"].removeprefix("Bearer ")

    return uuid.UUID(verify_token(token)["sid"])


def forge_refresh_token(session_id: uuid.UUID, secret: str, signature: str) -> str:
    return f"{session_id}.{secret}.{signature}"


async def run_concurrently(*coroutines: Coroutine[Any, Any, T]) -> list[T]:
    """Run the coroutines together and wait for all of them within the shared time limit.

    On any exit (a failed task, a timeout, an outer cancellation) the unfinished tasks are
    cancelled and awaited within the same time limit, so they release their sessions and
    connections before the call returns.
    """
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]

    try:
        return await asyncio.wait_for(asyncio.gather(*tasks), timeout=CONCURRENCY_TIMEOUT_SECONDS)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=CONCURRENCY_TIMEOUT_SECONDS
        )


async def count_row_lock_waiters(session_factory: async_sessionmaker[AsyncSession]) -> int:
    # A fresh session per call: pg_stat_activity is snapshotted once per transaction, so
    # polling inside one transaction would keep seeing the first snapshot
    async with session_factory() as session:
        return await session.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database()"
                " AND pid <> pg_backend_pid()"
                " AND wait_event_type = 'Lock'"
                " AND wait_event = ANY(:events)"
            ),
            {"events": ROW_LOCK_WAIT_EVENTS},
        )


async def wait_for_row_lock_waiters(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    expected_waiters: int = 1,
    timeout_seconds: float = CONCURRENCY_TIMEOUT_SECONDS,
) -> None:
    """Wait until at least expected_waiters transactions are blocked on a row lock.

    Counts every such connection in the current database, so it assumes no other test
    traffic. Raises TimeoutError, never returns quietly, when the waiters do not show up.
    """
    async with asyncio.timeout(timeout_seconds):
        while await count_row_lock_waiters(session_factory) < expected_waiters:
            await asyncio.sleep(LOCK_POLL_INTERVAL_SECONDS)


class FirstCallGate:
    """Holds the first call of an async function until released, and tells when it is held.

    The held call is the one that got there first: for a call made under a row lock, that is
    the request that took the lock. Later calls pass at once, and so does the case where no
    later call comes. A release that never comes fails the held call after the time limit.
    """

    def __init__(self, *, timeout_seconds: float = CONCURRENCY_TIMEOUT_SECONDS):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self._timeout_seconds = timeout_seconds
        self._first_call_taken = False

    def wrap(self, original: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def hold_first_call(*args: Any, **kwargs: Any) -> T:
            if not self._first_call_taken:
                self._first_call_taken = True
                self.entered.set()
                await asyncio.wait_for(self.release.wait(), timeout=self._timeout_seconds)

            return await original(*args, **kwargs)

        return hold_first_call


async def run_second_behind_first(
    first: Coroutine[Any, Any, T],
    second: Coroutine[Any, Any, U],
    *,
    gate: FirstCallGate,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[T, U]:
    """Run two requests so that the first holds the row lock while the second queues behind it.

    The second starts only once the first is held by the gate, and the gate is released once
    the second is really waiting for the lock.
    """

    async def start_second_when_first_is_held() -> U:
        try:
            await asyncio.wait_for(gate.entered.wait(), timeout=CONCURRENCY_TIMEOUT_SECONDS)
        except BaseException:
            # Never started, so it must be closed or it is reported as never awaited
            second.close()
            raise

        return await second

    async def release_when_second_waits() -> None:
        try:
            await wait_for_row_lock_waiters(session_factory)
        finally:
            gate.release.set()

    first_result, second_result, _ = await run_concurrently(
        first, start_second_when_first_is_held(), release_when_second_waits()
    )

    return first_result, second_result


def assert_field_error(
    response: Response,
    code: ErrorCode,
    loc: list[str | int],
    item_code: str | None = None,
    *,
    detail: str | None = None,
) -> None:
    body = response.json()

    assert body["code"] == code
    assert body["errors"] == [
        {
            "loc": loc,
            "code": code if item_code is None else item_code,
            "detail": body["detail"] if detail is None else detail,
        }
    ]


def assert_no_field_errors(response: Response, code: ErrorCode) -> None:
    body = response.json()

    assert body["code"] == code
    assert "errors" not in body
    assert isinstance(body["detail"], str)


def assert_validation_error(
    response: Response,
    loc: list[str | int],
    item_code: FieldErrorCode,
) -> None:
    body = response.json()

    assert body["code"] == ErrorCode.VALIDATION_FAILED
    assert body["detail"] == "Request validation failed"
    assert len(body["errors"]) == 1
    assert body["errors"][0]["loc"] == loc
    assert body["errors"][0]["code"] == item_code
    assert isinstance(body["errors"][0]["detail"], str)


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


def category_payload(
    name: str = "Test category", category_type: CategoryType = CategoryType.ANY
) -> dict[str, str]:
    return {"name": name, "type": category_type.value}


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
    description: str | None = None,
    splits: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "amount": amount,
        "type": template_type,
        "currency_code": currency_code,
        "category_id": category_id,
        "description": description,
    }

    if splits is not None:
        payload["splits"] = splits

    return payload


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
    splits: list[dict[str, object]] | None = None,
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

    if splits is not None:
        payload["splits"] = splits

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


def split_payload(
    category_id: int | None = None,
    amount: str = "500.00",
    description: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"amount": amount}

    if category_id is not None:
        payload["category_id"] = category_id
    if description is not None:
        payload["description"] = description

    return payload
