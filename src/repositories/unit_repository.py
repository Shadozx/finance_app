from sqlalchemy import select
from sqlalchemy.orm import Session

from src.exceptions import EntityNotFoundException
from src.models import Unit


class UnitRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_all(self):
        query = select(Unit)
        return self.session.execute(query).scalars().all()

    def get_by_id(self, id: int):
        query = select(Unit).where(Unit.id == id)
        result = self.session.execute(query).scalars().first()

        if result:
            return result
        else:
            raise EntityNotFoundException(entity_name="Unit", entity_id=id)

    def save(self, new_unit: Unit):
        self.session.add(new_unit)
        self.session.commit()

        self.session.refresh(new_unit)

        return new_unit

    def remove(self, id: int):
        unit = self.get_by_id(id)

        self.session.delete(unit)
        self.session.commit()
