import pytest

from app.models import USABLE_CATEGORY_TYPES, CategoryType, TransactionType

OPPOSITE_CATEGORY_TYPE = {
    TransactionType.EXPENSE: CategoryType.INCOME,
    TransactionType.INCOME: CategoryType.EXPENSE,
}


class TestUsableCategoryTypes:
    @pytest.mark.parametrize("direction", list(TransactionType))
    def test_every_direction_is_covered(self, direction: TransactionType):
        assert USABLE_CATEGORY_TYPES[direction]

    @pytest.mark.parametrize("direction", list(TransactionType))
    def test_any_serves_every_direction(self, direction: TransactionType):
        assert CategoryType.ANY in USABLE_CATEGORY_TYPES[direction]

    @pytest.mark.parametrize("direction", list(TransactionType))
    def test_opposite_type_is_excluded(self, direction: TransactionType):
        assert OPPOSITE_CATEGORY_TYPE[direction] not in USABLE_CATEGORY_TYPES[direction]
