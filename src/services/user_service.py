from sqlalchemy.orm import Session

from src.models import User
from src.repositories import UserRepository


class UserService:
    def __init__(self, session: Session):
        self.user_repository = UserRepository(session)

    def get_all(self):
        return self.user_repository.get_all()

    def get_by_id(self, id: int):
        return self.user_repository.get_by_id(id)

    def create(self, data: User):
        return self.user_repository.save(data)

    def delete(self, id: int):
        self.user_repository.remove(id)
