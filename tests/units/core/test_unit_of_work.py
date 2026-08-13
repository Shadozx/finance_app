import pytest
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import UnitOfWork


@pytest.fixture
def session(mocker: MockerFixture):
    return mocker.AsyncMock(spec=AsyncSession)


async def test_commit_delegates_to_session(session: AsyncSession):
    unit_of_work = UnitOfWork(session=session)

    await unit_of_work.commit()

    session.commit.assert_awaited_once()

async def test_rollback_delegates_to_session(session: AsyncSession):
    unit_of_work = UnitOfWork(session=session)

    await unit_of_work.rollback()

    session.rollback.assert_awaited_once()


