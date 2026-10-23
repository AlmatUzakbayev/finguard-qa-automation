"""The API contract as the tests understand it, written independently from app/schemas.py.

If the tests imported the application's own schemas, a breaking change in the app
would change the "expected" contract too and the tests would never notice.
extra="forbid" makes an unexpected field (for example a leaked password_hash) fail.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

# Money must be a JSON string with exactly two decimals, e.g. "100.00".
Money = Field(pattern=r"^-?\d+\.\d{2}$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserContract(Strict):
    id: StrictInt
    email: StrictStr
    full_name: StrictStr
    created_at: datetime


class TokenContract(Strict):
    access_token: StrictStr
    token_type: Literal["bearer"]
    expires_in: StrictInt


class AccountContract(Strict):
    id: StrictInt
    currency: Literal["KZT", "USD", "EUR"]
    balance: StrictStr = Money
    created_at: datetime


class BalanceContract(Strict):
    account_id: StrictInt
    currency: Literal["KZT", "USD", "EUR"]
    balance: StrictStr = Money


class TransferContract(Strict):
    id: StrictInt
    from_account_id: StrictInt
    to_account_id: StrictInt
    amount: StrictStr = Money
    description: StrictStr | None
    created_at: datetime


class HistoryEntryContract(Strict):
    id: StrictInt
    type: Literal["DEPOSIT", "TRANSFER"]
    direction: Literal["CREDIT", "DEBIT"]
    amount: StrictStr = Money
    counterparty_account_id: StrictInt | None
    description: StrictStr | None
    created_at: datetime


class ErrorContract(BaseModel):
    # "errors" is present only for VALIDATION_ERROR, so extra fields are allowed here.
    code: StrictStr
    detail: StrictStr
