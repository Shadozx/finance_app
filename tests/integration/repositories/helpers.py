from app.models import Transaction

def make_transaction(**kwargs) -> Transaction:
    """Transaction with settled fields defaulted to the operation amount.

    Cross-currency cases pass settled_amount explicitly.
    """
    kwargs.setdefault("settled_amount", kwargs["amount"])
    kwargs.setdefault("settled_currency_code", kwargs["currency_code"])
    return Transaction(**kwargs)
