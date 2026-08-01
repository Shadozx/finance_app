from typing import TypedDict


class UserData(TypedDict):
    id: int
    email: str
    username: str
    password: str


class AuthenticatedUser(TypedDict):
    user: UserData
    headers: dict[str, str]


class CategoryData(TypedDict):
    id: int
    name: str
    user_id: int
    created_at: str
    archived_at: str | None


class CurrencyData(TypedDict):
    code: str
    name: str
    symbol: str
    is_active: bool


class TransactionTemplateData(TypedDict):
    id: int
    name: str
    amount: str
    type: str
    currency_code: str
    category_id: int | None
    description: str | None
    user_id: int
    created_at: str

class TransactionData(TypedDict):
    id: int
    date: str
    amount: str
    type: str
    kind: str
    currency_code: str
    category_id: int | None
    description: str | None
    user_id: int
    account_id: int

class BudgetData(TypedDict):
    id: int
    name: str | None
    amount: str
    currency_code: str
    category_id: int
    start_date: str
    end_date: str

class AccountData(TypedDict):
    id: int
    name: str
    user_id: int
    currency_code: str
    created_at: str
    archived_at: str | None

    balance: str
