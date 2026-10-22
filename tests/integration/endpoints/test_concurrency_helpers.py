import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Currency
from tests.integration.endpoints.helpers import (
    CONCURRENCY_TIMEOUT_SECONDS,
    FirstCallGate,
    run_concurrently,
    wait_for_row_lock_waiters,
)

CURRENCY_CODE = "USD"
CURRENCY_SYMBOL = "$"
ORIGINAL_CURRENCY_NAME = "US Dollar"
UPDATED_CURRENCY_NAME = "Updated Dollar"

# Short on purpose: nobody queues in the timeout test, so a full wait would be wasted
SHORT_TIMEOUT_SECONDS = 0.2

FIRST_VALUE = "first"
SECOND_VALUE = "second"


class TestWaitForRowLockWaiters:
    async def test_waiter_reads_state_committed_by_lock_holder(
        self,
        independent_session_factory: async_sessionmaker[AsyncSession],
    ):
        async with independent_session_factory.begin() as session:
            session.add(
                Currency(
                    code=CURRENCY_CODE,
                    name=ORIGINAL_CURRENCY_NAME,
                    symbol=CURRENCY_SYMBOL,
                    is_active=True,
                )
            )

        lock_query = select(Currency).where(Currency.code == CURRENCY_CODE).with_for_update()

        # The outer context closes the holder on any exit, even if the release below never runs
        async with independent_session_factory() as holder_session:
            holder_currency = (await holder_session.scalars(lock_query)).one()
            holder_currency.name = UPDATED_CURRENCY_NAME
            await holder_session.flush()

            async def read_as_waiter() -> str:
                async with independent_session_factory() as waiter_session:
                    return (await waiter_session.scalars(lock_query)).one().name

            async def release_holder_when_waiter_queued() -> None:
                # Release the lock on every path, so the waiter never queues behind a dead test
                try:
                    await wait_for_row_lock_waiters(independent_session_factory)
                    await holder_session.commit()
                except BaseException:
                    await holder_session.rollback()
                    raise

            waiter_name, _ = await run_concurrently(
                read_as_waiter(), release_holder_when_waiter_queued()
            )

        assert waiter_name == UPDATED_CURRENCY_NAME

    async def test_times_out_when_nobody_waits(
        self,
        independent_session_factory: async_sessionmaker[AsyncSession],
    ):
        with pytest.raises(TimeoutError):
            await wait_for_row_lock_waiters(
                independent_session_factory, timeout_seconds=SHORT_TIMEOUT_SECONDS
            )


class TestFirstCallGate:
    async def test_holds_only_the_first_call_until_released(self):
        calls = []

        async def record(value: str) -> str:
            calls.append(value)
            return value

        gate = FirstCallGate()
        wrapped = gate.wrap(record)

        async def check_while_first_call_is_held():
            try:
                await asyncio.wait_for(gate.entered.wait(), timeout=CONCURRENCY_TIMEOUT_SECONDS)
                assert calls == []

                assert await wrapped(SECOND_VALUE) == SECOND_VALUE
                assert calls == [SECOND_VALUE]
            finally:
                gate.release.set()

        first_result, _ = await run_concurrently(
            wrapped(FIRST_VALUE), check_while_first_call_is_held()
        )

        assert first_result == FIRST_VALUE
        assert calls == [SECOND_VALUE, FIRST_VALUE]

    async def test_fails_the_first_call_when_it_is_never_released(self):
        calls = []

        async def record(value: str) -> str:
            calls.append(value)
            return value

        gate = FirstCallGate(timeout_seconds=SHORT_TIMEOUT_SECONDS)

        with pytest.raises(TimeoutError):
            await gate.wrap(record)(FIRST_VALUE)

        assert gate.entered.is_set()
        assert calls == []
