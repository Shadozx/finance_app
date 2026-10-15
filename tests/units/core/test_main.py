import pytest
from pytest_mock import MockerFixture

from app.main import app


@pytest.mark.parametrize("failed", [False, True], ids=["normal-exit", "exception"])
async def test_lifespan_shuts_down_password_hasher(mocker: MockerFixture, failed: bool):
    shutdown = mocker.patch("app.main.password_hasher.shutdown")
    error = RuntimeError("Application failed")

    if failed:
        with pytest.raises(RuntimeError) as exc_info:
            async with app.router.lifespan_context(app):
                shutdown.assert_not_called()
                raise error
        assert exc_info.value is error
    else:
        async with app.router.lifespan_context(app):
            shutdown.assert_not_called()

    shutdown.assert_called_once_with()
