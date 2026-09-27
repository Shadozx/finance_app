from pydantic import BaseModel

from app.core.error_codes import ErrorCode


class ErrorItem(BaseModel):
    loc: list[str | int]
    code: str
    detail: str


class ErrorResponse(BaseModel):
    status: int
    code: ErrorCode
    detail: str
    errors: list[ErrorItem] | None = None
