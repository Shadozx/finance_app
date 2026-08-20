import structlog

from app.core import UnitOfWork
from app.core.exceptions import AuthenticationException, ValidationException, ValueExistsException
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.repositories import UserRepository
from app.schemas import PasswordUpdate, UserCreate, UserLogin, UsernameUpdate, UserResponse
from app.services import validators

logger = structlog.get_logger()


class UserService:
    def __init__(self, user_repository: UserRepository, unit_of_work: UnitOfWork):
        self.user_repository = user_repository
        self.unit_of_work = unit_of_work

    async def register_user(self, user: UserCreate) -> UserResponse:
        if await self.user_repository.get_by_email(user.email):
            raise ValueExistsException("User with this email already exists")

        if await self.user_repository.get_by_username(user.username):
            raise ValueExistsException("User with this username already exists")

        new_user = User(
            username=user.username, email=user.email, hashed_password=hash_password(user.password)
        )

        created_user = await self.user_repository.add(new_user)

        await self.unit_of_work.commit()

        logger.info("user_register_success", user_id=created_user.id)

        return UserResponse.model_validate(created_user)

    async def authenticate(self, user: UserLogin) -> str:
        existing_user = await self.user_repository.get_by_email(user.email)

        if not existing_user or not verify_password(user.password, existing_user.hashed_password):
            logger.warning("user_authenticate_failed", email=user.email)

            raise AuthenticationException("Invalid email or password")

        logger.info("user_authenticate_success", user_id=existing_user.id, email=user.email)

        return create_access_token({"sub": str(existing_user.id)})

    async def update_username(self, data: UsernameUpdate, user_id: int) -> UserResponse:
        existing_user = await validators.validate_user(self.user_repository, user_id)

        duplicate_username_user = await self.user_repository.get_by_username(data.new_username)

        if duplicate_username_user and duplicate_username_user.id != user_id:
            logger.info("username_update_failed", user_id=user_id, new_username=data.new_username)

            raise ValueExistsException("Username is already taken")

        existing_user.username = data.new_username
        updated_user = await self.user_repository.update(existing_user)

        await self.unit_of_work.commit()

        logger.info(
            "username_update_success", user_id=updated_user.id, new_username=data.new_username
        )

        return UserResponse.model_validate(updated_user)

    async def update_password(self, data: PasswordUpdate, user_id: int) -> None:
        existing_user = await validators.validate_user(self.user_repository, user_id)

        if data.current_password == data.new_password:
            raise ValidationException("New password must be different from current password")

        if not verify_password(data.current_password, existing_user.hashed_password):
            logger.warning("password_update_failed", user_id=user_id)

            raise AuthenticationException("Current password is incorrect")

        existing_user.hashed_password = hash_password(data.new_password)

        await self.user_repository.update(existing_user)

        await self.unit_of_work.commit()

        logger.info("password_update_success", user_id=existing_user.id)
