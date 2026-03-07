from app.models import User
from app.repositories import UserRepository
from app.schemas import UserCreate, UserResponse, UserLogin
from app.core.security import create_access_token, verify_password, hash_password
from app.core.exceptions import AuthenticationException, ValueExistsException


class UserService:

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def register_user(
            self,
            user: UserCreate
    ) -> UserResponse:
        if await self.user_repository.get_by_email(user.email):
            raise ValueExistsException("User with this email already exists")

        if await self.user_repository.get_by_username(user.username):
            raise ValueExistsException("User with this username already exists")

        new_user = User(
            username=user.username,
            email=user.email,
            hashed_password=hash_password(user.password)
        )

        created_user = await self.user_repository.create(new_user)
        return UserResponse.model_validate(created_user)

    async def authenticate(
            self,
            user: UserLogin
    ) -> str:
        existing_user = await self.user_repository.get_by_email(user.email)

        if not existing_user or not verify_password(user.password, existing_user.hashed_password):
            raise AuthenticationException("Invalid email or password")

        return create_access_token({"sub": str(existing_user.id)})
