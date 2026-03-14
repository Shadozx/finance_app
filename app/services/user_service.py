from app.models import User
from app.repositories import UserRepository
from app.schemas import UserCreate, UserResponse, UserLogin, UsernameUpdate, PasswordUpdate
from app.core.security import create_access_token, verify_password, hash_password
from app.core.exceptions import AuthenticationException, ValueExistsException, ValidationException


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

    async def update_username(
            self,
            data: UsernameUpdate,
            user_id: int
    ) -> UserResponse:
        existing_user = await self.user_repository.get_by_id(user_id)

        duplicate_username_user = await self.user_repository.get_by_username(data.new_username)

        if duplicate_username_user and duplicate_username_user.id != user_id:
            raise ValueExistsException("Username is already taken")

        existing_user.username = data.new_username

        return UserResponse.model_validate(await self.user_repository.update(existing_user))

    async def update_password(
            self,
            data: PasswordUpdate,
            user_id: int
    ) -> None:
        existing_user = await self.user_repository.get_by_id(user_id)

        if data.current_password == data.new_password:
            raise ValidationException("New password must be different from current password")

        if not verify_password(data.current_password, existing_user.hashed_password):
            raise AuthenticationException("Current password is incorrect")

        existing_user.hashed_password = hash_password(data.new_password)

        await self.user_repository.update(existing_user)
