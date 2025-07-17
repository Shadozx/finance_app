from sqlalchemy import select
from sqlalchemy.orm import Session

from src.exceptions import EntityNotFoundException
from src.models import User


class UserRepository:

    def __init__(self, session: Session):
        self.session = session

    def get_all(self):
        query = select(User)
        return self.session.execute(query).scalars().all()

    def get_by_id(self, id: int):
        query = select(User).where(User.id == id)
        result = self.session.execute(query).scalars().first()

        if result:
            return result
        else:
            raise EntityNotFoundException(entity_name="User", entity_id=id)

    def save(self, user: User):
        self.session.add(user)
        self.session.commit()

        self.session.refresh(user)

        return user

    def remove(self, user_id: int):
        user = self.get_by_id(user_id)
        print(user)
        self.session.delete(user)
        self.session.commit()

    # def update(self, user: User):
    #     self.session.add(user)
    #     self.session.commit()