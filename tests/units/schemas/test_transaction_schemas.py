from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import TransactionType
from app.schemas import TransactionCreate


class TestTransactionCreate:
    def test_without_splits_success(self):
        t = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("1000.00"),
            currency_code="UAH",
            category_id=7,
            account_id=1,
            date=date(2026, 8, 20),
        )
        assert t.splits is None
        assert t.category_id == 7

    def test_with_splits_success(self):
        t = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("1000.00"),
            currency_code="UAH",
            account_id=1,
            date=date(2026, 8, 20),
            splits=[
                {"category_id": 7, "amount": Decimal("800.00"), "description": "Groceries"},
                {"category_id": 12, "amount": Decimal("200.00"), "description": "Household"},
            ],
        )
        assert len(t.splits) == 2
        assert t.category_id is None
        assert t.splits[0].description == "Groceries"

    def test_split_without_category_allowed(self):
        t = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("1000.00"),
            currency_code="UAH",
            account_id=1,
            date=date(2026, 8, 20),
            splits=[
                {"category_id": None, "amount": Decimal("600.00")},
                {"category_id": 7, "amount": Decimal("400.00")},
            ],
        )
        assert t.splits[0].category_id is None

    def test_splits_with_own_category_raises(self):
        with pytest.raises(ValidationError, match="cannot have its own category"):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("1000.00"),
                currency_code="UAH",
                category_id=7,
                account_id=1,
                date=date(2026, 8, 20),
                splits=[
                    {"category_id": 7, "amount": Decimal("800.00")},
                    {"category_id": 12, "amount": Decimal("200.00")},
                ],
            )

    def test_splits_sum_below_amount_mismatch(self):
        with pytest.raises(ValidationError, match="must add up to"):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("1000.00"),
                currency_code="UAH",
                account_id=1,
                date=date(2026, 8, 20),
                splits=[
                    {"category_id": 7, "amount": Decimal("800.00")},
                    {"category_id": 12, "amount": Decimal("100.00")},
                ],
            )

    def test_splits_sum_above_amount_mismatch(self):
        with pytest.raises(ValidationError, match="must add up to"):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("1000.00"),
                currency_code="UAH",
                account_id=1,
                date=date(2026, 8, 20),
                splits=[
                    {"category_id": 7, "amount": Decimal("800.00")},
                    {"category_id": 12, "amount": Decimal("300.00")},
                ],
            )

    def test_splits_sum_off_by_one_cent_mismatch(self):
        with pytest.raises(ValidationError, match="must add up to"):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("1000.00"),
                currency_code="UAH",
                account_id=1,
                date=date(2026, 8, 20),
                splits=[
                    {"category_id": 7, "amount": Decimal("800.00")},
                    {"category_id": 12, "amount": Decimal("199.99")},
                ],
            )

    def test_single_split_raises(self):
        with pytest.raises(ValidationError):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("1000.00"),
                currency_code="UAH",
                account_id=1,
                date=date(2026, 8, 20),
                splits=[{"category_id": 7, "amount": Decimal("1000.00")}],
            )

    def test_empty_splits_raises(self):
        with pytest.raises(ValidationError):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("1000.00"),
                currency_code="UAH",
                account_id=1,
                date=date(2026, 8, 20),
                splits=[],
            )

    def test_fifty_splits_allowed(self):
        t = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("50.00"),
            currency_code="UAH",
            account_id=1,
            date=date(2026, 8, 20),
            splits=[{"category_id": 7, "amount": Decimal("1.00")} for _ in range(50)],
        )
        assert len(t.splits) == 50

    def test_too_many_splits_raises(self):
        with pytest.raises(ValidationError):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("51.00"),
                currency_code="UAH",
                account_id=1,
                date=date(2026, 8, 20),
                splits=[{"category_id": 7, "amount": Decimal("1.00")} for _ in range(51)],
            )

    def test_negative_split_amount_raises(self):
        with pytest.raises(ValidationError):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("1000.00"),
                currency_code="UAH",
                account_id=1,
                date=date(2026, 8, 20),
                splits=[
                    {"category_id": 7, "amount": Decimal("1100.00")},
                    {"category_id": 12, "amount": Decimal("-100.00")},
                ],
            )

    def test_split_description_too_long_raises(self):
        with pytest.raises(ValidationError):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("1000.00"),
                currency_code="UAH",
                account_id=1,
                date=date(2026, 8, 20),
                splits=[
                    {"category_id": 7, "amount": Decimal("800.00"), "description": "x" * 1025},
                    {"category_id": 12, "amount": Decimal("200.00")},
                ],
            )

    def test_zero_amount_with_splits_raises(self):
        with pytest.raises(ValidationError, match="zero amount"):
            TransactionCreate(
                type=TransactionType.EXPENSE,
                amount=Decimal("0"),
                currency_code="UAH",
                account_id=1,
                date=date(2026, 8, 20),
                splits=[
                    {"category_id": 7, "amount": Decimal("0")},
                    {"category_id": 12, "amount": Decimal("0")},
                ],
            )

    def test_zero_amount_without_splits_allowed(self):
        t = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=Decimal("0"),
            currency_code="UAH",
            category_id=7,
            account_id=1,
            date=date(2026, 8, 20),
        )
        assert t.amount == Decimal("0")
