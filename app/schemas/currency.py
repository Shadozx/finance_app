from pydantic import BaseModel, ConfigDict


class CurrencyResponse(BaseModel):
    code: str

    symbol: str

    name: str

    is_active: bool

    model_config = ConfigDict(from_attributes=True)
