from sqlalchemy.orm import Session

from src.models import Unit
from src.repositories import UnitRepository


class UnitService:

    def __init__(self, session: Session):
        self.unit_repo = UnitRepository(session)

    def get_all(self):
        return self.unit_repo.get_all()

    def get_by_id(self, id: int):
        return self.unit_repo.get_by_id(id)

    def create(self, data: Unit):
        return self.unit_repo.save(data)

    def delete(self, id: int):
        self.unit_repo.remove(id)
