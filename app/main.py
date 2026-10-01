import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.api.v1.endpoints import (
    accounts,
    auth,
    budgets,
    categories,
    currencies,
    health,
    statistics,
    transaction_templates,
    transactions,
    transfers,
    users,
)
from app.core.config import Environment, settings
from app.core.exception_handlers import (
    app_exception_handler,
    global_exception_handler,
    http_exception_handler,
    integrity_error_handler,
    request_validation_handler,
)
from app.core.exceptions import REQUEST_VALIDATION_FAILED_MESSAGE, AppException
from app.core.logging_config import setup_logging
from app.core.middleware import RequestIDMiddleware, UnhandledExceptionMiddleware
from app.core.openapi import configure_openapi
from app.core.rate_limiter import limiter
from app.schemas.error import ErrorResponse

is_prod = settings.ENVIRONMENT == Environment.PROD

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
    openapi_url=None if is_prod else "/openapi.json",
    responses={
        422: {
            "model": ErrorResponse,
            "description": REQUEST_VALIDATION_FAILED_MESSAGE,
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            },
        }
    },
)

setup_logging(settings)

app.state.limiter = limiter

app.add_middleware(SlowAPIMiddleware)

# Inside RequestIDMiddleware and CORSMiddleware, so a 500 passes through both
# and is logged before the request context is cleared
app.add_middleware(UnhandledExceptionMiddleware)

app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(currencies.router, prefix="/api/v1")
app.include_router(transaction_templates.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(transfers.router, prefix="/api/v1")
app.include_router(statistics.router, prefix="/api/v1")
app.include_router(budgets.router, prefix="/api/v1")
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")

app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]

# Starlette types handler as (Request, Exception); ours narrows to AppException —
# safe, Starlette only dispatches matching type
app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, global_exception_handler)


configure_openapi(app)

if __name__ == "__main__":
    # uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=[os.path.abspath("app")])
    uvicorn.run("app.main:app", host="0.0.0.0", port=8020, reload=False, access_log=False)

# test user
# {
#   "username": "user1234",
#   "email": "testuser1234@gmail.com",
#   "password": "qWerty12#"
# }
# {
#   "username": "testuser123456789",
#   "email": "user@example.com",
#   "password": "userTest1"
# }
