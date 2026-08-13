from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    """Owns the transaction boundary for the service layer.

    AsyncSession is the actual unit of work; this class only decides *when* the
    operation ends. It exists separately because services depend on repositories,
    never on AsyncSession.

    Intentionally minimal: no repositories, no execute/add/flush. The session is
    private so services cannot run SQL behind the repositories.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
