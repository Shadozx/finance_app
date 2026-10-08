from pydantic import BaseModel, Field

REFRESH_TOKEN_MAX_LENGTH = 512


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=REFRESH_TOKEN_MAX_LENGTH)
