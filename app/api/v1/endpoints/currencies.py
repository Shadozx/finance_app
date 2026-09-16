from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_currency_service
from app.schemas import CurrencyResponse, Page
from app.services import CurrencyService

router = APIRouter(prefix="/currencies", tags=["currencies"])


@router.get("", response_model=Page[CurrencyResponse])
async def get_active_currencies(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    currency_service: CurrencyService = Depends(get_currency_service),
):
    return await currency_service.get_active_currencies(limit, offset)


@router.get("/{currency_code}", response_model=CurrencyResponse)
async def get_currency(
    currency_code: str, currency_service: CurrencyService = Depends(get_currency_service)
) -> CurrencyResponse:
    return await currency_service.get_currency(currency_code)
