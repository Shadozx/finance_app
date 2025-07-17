from fastapi import APIRouter, Depends

from src.dependencies import get_session
from src.models import Category
from src.schemas import CategoryCreate, CategoryOut
from src.services import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/")
def get_categories(session = Depends(get_session)) -> list[CategoryOut]:
    category_service = CategoryService(session)
    return category_service.get_all()


@router.post("/")
def create_category(new_category: CategoryCreate, session = Depends(get_session)) -> CategoryOut:
    # result = list(filter(lambda c: c.name == new_category.name, categories))

    # if len(result) > 0:
    #     raise HTTPException(status_code=409, detail="Category already exists")
    category = Category(
        **new_category.model_dump(),
    )

    category_service = CategoryService(session)

    return CategoryOut.model_validate(category_service.create(category))


    # category = CategoryOut(**new_category.model_dump(), id=len(categories) + 1, created_at=datetime.now())
    # categories.append(category)

    # return category

@router.delete("/{id}")
def get_category_by_id(id: int, session = Depends(get_session)) -> CategoryOut:
    category_service = CategoryService(session)

    return CategoryOut.model_validate(category_service.get_by_id(id))


@router.delete("/{id}")
def delete_category_by_id(id: int, session = Depends(get_session)):
    # category_to_delete = next((c for c in categories if c.id == id), None)
    #
    # if category_to_delete is None:
    #     raise HTTPException(status_code=404, detail="Category not found")
    #
    # categories.remove(category_to_delete)

    category_service = CategoryService(session)

    category_service.delete(id)

    return {"status": "success"}
