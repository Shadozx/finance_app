from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UserSessionResponse(BaseModel):
    id: UUID
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    is_current: bool
