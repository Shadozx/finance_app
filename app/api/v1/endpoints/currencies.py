from fastapi import APIRouter, Depends

from app.api.dependencies import get_currency_service
from app.schemas import CurrencyResponse
from app.services import CurrencyService

router = APIRouter(prefix="/currencies", tags=["currencies"])


@router.get("", response_model=list[CurrencyResponse])
async def get_active_currencies(currency_service: CurrencyService = Depends(get_currency_service)):
    return await currency_service.get_active_currencies()


@router.get("/{currency_code}", response_model=CurrencyResponse)
async def get_currency(
    currency_code: str, currency_service: CurrencyService = Depends(get_currency_service)
) -> CurrencyResponse:
    return await currency_service.get_currency(currency_code)
