"""Category taxonomy. `kind` drives cash-flow maths (income vs spend vs transfer)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    kind: str  # income | expense | transfer
    icon: str  # lucide icon name used by the UI


CATEGORIES: list[Category] = [
    Category("salary", "Salary & Income", "income", "briefcase"),
    Category("interest", "Interest", "income", "percent"),
    Category("refund", "Refunds & Reversals", "income", "undo-2"),
    Category("transfer_in", "Transfers In", "transfer", "arrow-down-left"),
    Category("cash_deposit", "Cash Deposit", "transfer", "piggy-bank"),
    Category("transfer_out", "Transfers Out", "transfer", "arrow-up-right"),
    Category("food", "Food & Dining", "expense", "utensils"),
    Category("groceries", "Groceries", "expense", "shopping-basket"),
    Category("shopping", "Shopping", "expense", "shopping-bag"),
    Category("travel", "Travel & Transport", "expense", "plane"),
    Category("fuel", "Fuel", "expense", "fuel"),
    Category("utilities", "Utilities & Bills", "expense", "zap"),
    Category("rent", "Rent & Housing", "expense", "home"),
    Category("loan", "Loan & EMI", "expense", "landmark"),
    Category("investment", "Investments", "transfer", "trending-up"),
    Category("insurance", "Insurance", "expense", "shield"),
    Category("health", "Healthcare", "expense", "heart-pulse"),
    Category("education", "Education", "expense", "graduation-cap"),
    Category("entertainment", "Entertainment & Subscriptions", "expense", "clapperboard"),
    Category("wallet", "Wallet Top-up", "transfer", "wallet"),
    Category("cash_withdrawal", "Cash Withdrawal", "expense", "banknote"),
    Category("charges", "Bank Charges & Fees", "expense", "receipt"),
    Category("tax", "Taxes", "expense", "scale"),
    Category("card_payment", "Credit Card Payment", "transfer", "credit-card"),
    Category("other", "Other", "expense", "circle-help"),
]
BY_ID = {c.id: c for c in CATEGORIES}
IDS = [c.id for c in CATEGORIES]


def name(cat_id: str) -> str:
    return BY_ID.get(cat_id, BY_ID["other"]).name
