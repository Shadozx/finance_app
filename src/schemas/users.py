from pydantic import BaseModel


# --- Pydantic-схеми ---
class UserCreate(BaseModel):
    username: str
    email: str

    password: str


class UserOut(UserCreate):
    id: int


    model_config = {
        'from_attributes': True
    }
