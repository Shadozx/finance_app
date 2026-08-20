from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency, TransactionTemplate, TransactionType, User
from app.repositories import TransactionTemplateRepository, UserRepository


@pytest.fixture
async def transaction_template(
    transaction_template_repository: TransactionTemplateRepository,
    user: User,
    uah_currency: Currency,
):
    return await transaction_template_repository.add(
        TransactionTemplate(
            name="Morning Coffee",
            type=TransactionType.EXPENSE,
            description="Morning Coffee near work",
            amount=Decimal("100.00"),
            currency_code=uah_currency.code,
            user_id=user.id,
        )
    )


class TestAdd:
    async def test_add(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        user: User,
        uah_currency: Currency,
    ):
        template = TransactionTemplate(
            name="Morning Coffee",
            type=TransactionType.EXPENSE,
            description="Morning Coffee",
            amount=Decimal("100.00"),
            currency_code=uah_currency.code,
            user_id=user.id,
        )

        created_template = await transaction_template_repository.add(template)

        assert created_template.id is not None
        assert created_template.name == template.name
        assert created_template.user_id == user.id
        assert created_template.created_at is not None

    async def test_add_duplicate_name_same_user(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        transaction_template: TransactionTemplate,
    ):
        with pytest.raises(IntegrityError):
            await transaction_template_repository.add(
                TransactionTemplate(
                    name=transaction_template.name,
                    type=transaction_template.type,
                    amount=Decimal("200.00"),
                    currency_code=transaction_template.currency_code,
                    user_id=transaction_template.user_id,
                    description="Morning Coffee",
                )
            )


class TestGetById:
    async def test_get_by_id(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        transaction_template: TransactionTemplate,
    ):
        found_template = await transaction_template_repository.get_by_id(transaction_template.id)

        assert found_template.id == transaction_template.id
        assert found_template.name == transaction_template.name
        assert found_template.user_id == transaction_template.user_id

    async def test_get_by_id_not_found(
        self,
        transaction_template_repository: TransactionTemplateRepository,
    ):
        found_template = await transaction_template_repository.get_by_id(999)

        assert found_template is None


class TestGetByUser:
    @pytest.fixture
    async def transaction_templates(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        user: User,
        uah_currency: Currency,
    ):
        t1 = await transaction_template_repository.add(
            TransactionTemplate(
                name="Salary",
                type=TransactionType.INCOME,
                amount=Decimal("35000.00"),
                description="Salary",
                currency_code=uah_currency.code,
                user_id=user.id,
            )
        )

        t2 = await transaction_template_repository.add(
            TransactionTemplate(
                name="Coffee",
                type=TransactionType.EXPENSE,
                amount=Decimal("150.00"),
                description="Coffee",
                currency_code=uah_currency.code,
                user_id=user.id,
            )
        )

        t3 = await transaction_template_repository.add(
            TransactionTemplate(
                name="Netflix subscription",
                type=TransactionType.EXPENSE,
                amount=Decimal("500.00"),
                description="Netflix",
                currency_code=uah_currency.code,
                user_id=user.id,
            )
        )

        t4 = await transaction_template_repository.add(
            TransactionTemplate(
                name="Freelance",
                type=TransactionType.INCOME,
                amount=Decimal("15000.00"),
                description="Freelance",
                currency_code=uah_currency.code,
                user_id=user.id,
            )
        )

        return [t1, t2, t3, t4]

    async def test_get_by_user(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        user: User,
        transaction_templates,
    ):
        user_transaction_templates = await transaction_template_repository.get_by_user(user.id)

        assert len(user_transaction_templates) == len(transaction_templates)

        assert all(t.user_id == user.id for t in user_transaction_templates)

    async def test_get_by_user_empty(
        self,
        test_session: AsyncSession,
        transaction_template_repository: TransactionTemplateRepository,
        user: User,
    ):
        user_transaction_templates = await transaction_template_repository.get_by_user(user.id)

        assert len(user_transaction_templates) == 0

    async def test_get_by_user_returns_only_own(
        self,
        test_session: AsyncSession,
        transaction_template_repository: TransactionTemplateRepository,
        user: User,
        transaction_template: TransactionTemplate,
        usd_currency: Currency,
    ):
        other_user_repository = UserRepository(test_session)
        other_user = await other_user_repository.add(
            User(
                email="other@test.com",
                username="other",
                hashed_password="hashed",
            )
        )

        await transaction_template_repository.add(
            TransactionTemplate(
                name="Netflix subscription",
                type=TransactionType.EXPENSE,
                amount=Decimal("50.00"),
                description="Netflix",
                currency_code=usd_currency.code,
                user_id=other_user.id,
            )
        )

        user_transaction_templates = await transaction_template_repository.get_by_user(user.id)

        assert len(user_transaction_templates) == 1

        assert user_transaction_templates[0].id == transaction_template.id
        assert user_transaction_templates[0].description == transaction_template.description
        assert user_transaction_templates[0].user_id == transaction_template.user_id

    async def test_pagination_limit(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        user: User,
        transaction_templates,
    ):
        limit = 2
        user_transaction_templates = await transaction_template_repository.get_by_user(
            user.id, limit=limit
        )

        assert len(user_transaction_templates) == limit

    async def test_pagination_offset(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        user: User,
        transaction_templates,
    ):
        offset = 2
        limit = len(transaction_templates) - offset
        user_transaction_templates = await transaction_template_repository.get_by_user(
            user.id, offset=offset
        )

        assert len(user_transaction_templates) == limit


class TestGetByUserAndName:
    async def test_get_by_user_and_name(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        transaction_template: TransactionTemplate,
    ):
        found_transaction_template = await transaction_template_repository.get_by_user_and_name(
            transaction_template.name, transaction_template.user_id
        )

        assert found_transaction_template.id == transaction_template.id
        assert found_transaction_template.name == transaction_template.name
        assert found_transaction_template.user_id == transaction_template.user_id

    async def test_get_by_user_and_name_not_found(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        user: User,
    ):
        found_transaction_template = await transaction_template_repository.get_by_user_and_name(
            "wrong name", user.id
        )

        assert found_transaction_template is None


class TestUpdate:
    async def test_update(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        transaction_template: TransactionTemplate,
    ):
        transaction_template.amount = Decimal("155.00")

        updated_transaction = await transaction_template_repository.update(transaction_template)

        assert updated_transaction.id == transaction_template.id
        assert updated_transaction.amount == transaction_template.amount

        found_transaction = await transaction_template_repository.get_by_id(transaction_template.id)
        assert found_transaction.amount == transaction_template.amount


class TestDelete:
    async def test_delete(
        self,
        transaction_template_repository: TransactionTemplateRepository,
        transaction_template: TransactionTemplate,
    ):
        await transaction_template_repository.delete(transaction_template)

        found_transaction = await transaction_template_repository.get_by_id(transaction_template.id)
        assert found_transaction is None
