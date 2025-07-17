from fastapi import APIRouter, Depends

from src.dependencies import get_session
from src.models import User
from src.schemas import UserOut, UserCreate
from src.services import UserService

router = APIRouter(prefix="/users", tags=["users"])


# @router.get("/test")
def route_test():
    return {"message": "Hello World"}


@router.get("/")
def get_all_users(session=Depends(get_session)) -> list[UserOut]:
    user_service = UserService(session)

    return [UserOut.model_validate(u) for u in user_service.get_all()]


@router.get("/{id}")
def get_user_by_id(id: int, session=Depends(get_session)) -> UserOut:
    user_service = UserService(session)

    return UserOut.model_validate(user_service.get_by_id(id))


@router.post("/")
def create_new_user(new_user: UserCreate, session=Depends(get_session)) -> UserOut:
    user_service = UserService(session)

    user = User(
        **new_user.model_dump()
    )

    return UserOut.model_validate(user_service.create(user))


@router.delete("/{id}")
def remove_user_by_id(id: int, session=Depends(get_session)):
    print("deleting user by id: ", id)
    user_service = UserService(session)
    user_service.delete(id)
    return {"message": "user deleted"}
