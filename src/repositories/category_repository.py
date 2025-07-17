from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.exceptions import EntityNotFoundException
from src.models import Category


class CategoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Category]:
        return self.session.execute(select(Category)).scalars().all()


    def get_category_by_id(self, category_id) -> Optional[Category]:
        query = select(Category).where(Category.id == category_id)
        result = self.session.execute(query).scalars().first()

        if result:
            return result
        else:
            raise EntityNotFoundException(entity_name="Category", entity_id=category_id)

    def get_category_by_name(self, category_name) -> Optional[Category]:
        query = select(Category).where(Category.name == category_name)
        return self.session.execute(query).scalars().first()

    def save(self, category_data: Category) -> Category:
        self.session.add(category_data)
        self.session.commit()
        self.session.refresh(category_data)

        return category_data

    def remove(self, category_id: int):
        category_data = self.get_category_by_id(category_id)
        self.session.delete(category_data)
        self.session.commit()

    def update(self, new_category_data) -> Category:

        old_category_data = self.get_category_by_id(new_category_data.id)

        if new_category_data.name and old_category_data.name != new_category_data.name:
            old_category_data.name = new_category_data.name

        self.session.commit()
        self.session.refresh(old_category_data)

        return old_category_data


