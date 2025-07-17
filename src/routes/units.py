
from fastapi import APIRouter, Depends

from src.dependencies import get_session
from src.models import Unit
from src.schemas import UnitCreate, UnitOut
from src.services import UnitService

router = APIRouter(prefix="/units", tags=["units"])

@router.get("/", response_model=list[UnitOut])
def get_units(session = Depends(get_session)) -> list[UnitOut]:
    unit_service = UnitService(session)
    return [UnitOut.model_validate(t) for t in unit_service.get_all()]

@router.post("/", response_model=UnitOut)
def create_unit(new_unit: UnitCreate, session = Depends(get_session)) -> UnitOut:
    unit = Unit(
        **new_unit.model_dump()
    )

    unit_service = UnitService(session)


    return UnitOut.model_validate(unit_service.create(unit))

@router.get("/{id}", response_model=UnitOut)
def read_unit(id: int, session = Depends(get_session)) -> UnitOut:

    unit_service = UnitService(session)

    return UnitOut.model_validate(unit_service.get_by_id(id))


@router.delete("/{id}", description="Delete a unit")
def delete_unit(id: int, session = Depends(get_session)):
    unit_service = UnitService(session)

    unit_service.delete(id)

    return {"status": "success"}