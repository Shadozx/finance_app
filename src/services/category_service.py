from sqlalchemy.orm import Session

from src.models import Category
from src.repositories import CategoryRepository


class CategoryService:

    def __init__(self, session: Session):
        self.category_repository = CategoryRepository(session)


    def get_all(self):
        return self.category_repository.get_all()

    def create(self, category: Category):
        return self.category_repository.save(category)

    def get_by_id(self, category_id: int):
        return self.category_repository.get_category_by_id(category_id)

    def delete(self, category_id: int):
        self.category_repository.remove(category_id)

