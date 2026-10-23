"""Request/response schemas (Pydantic v2).

Money values are Decimal. In JSON responses they are serialised as strings ("100.00")
so that clients never lose precision through floating-point parsing.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.config import get_settings

settings = get_settings()


def _to_cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


# A positive amount with at most 2 decimal places, e.g. "10.50". "0.001" is rejected.
Amount = Annotated[
    Decimal,
    Field(ge=settings.min_amount, max_digits=18, decimal_places=2),
    AfterValidator(_to_cents),
]

Currency = Literal["KZT", "USD", "EUR"]

# Primary keys are PostgreSQL INTEGER columns. Larger ids must be rejected during
# validation: passing them to the database raised an error and caused HTTP 500 (BUG-001).
MAX_DB_ID = 2_147_483_647
AccountIdField = Field(gt=0, le=MAX_DB_ID)


class RequestModel(BaseModel):
    # Unknown fields are an error: a typo like "ammount" must not be silently ignored.
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(RequestModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)


class LoginRequest(RequestModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    created_at: datetime


class AccountCreate(RequestModel):
    currency: Currency = "KZT"


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    currency: str
    balance: Decimal
    created_at: datetime


class BalanceOut(BaseModel):
    account_id: int
    currency: str
    balance: Decimal


class DepositRequest(RequestModel):
    amount: Annotated[Amount, Field(le=settings.max_deposit_amount)]


class TransferRequest(RequestModel):
    from_account_id: int = AccountIdField
    to_account_id: int = AccountIdField
    amount: Annotated[Amount, Field(le=settings.max_transfer_amount)]
    description: str | None = Field(default=None, max_length=140)

    @model_validator(mode="after")
    def _different_accounts(self) -> "TransferRequest":
        if self.from_account_id == self.to_account_id:
            raise ValueError("from_account_id and to_account_id must be different")
        return self


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_account_id: int
    to_account_id: int
    amount: Decimal
    description: str | None
    created_at: datetime


class HistoryEntry(BaseModel):
    id: int
    type: Literal["DEPOSIT", "TRANSFER"]
    direction: Literal["CREDIT", "DEBIT"]
    amount: Decimal
    counterparty_account_id: int | None
    description: str | None
    created_at: datetime


class ErrorOut(BaseModel):
    code: str
    detail: str
