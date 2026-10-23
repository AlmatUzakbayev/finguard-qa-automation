from typing import Annotated

from fastapi import APIRouter, Path, Query
from sqlalchemy import select

from app import services
from app.deps import CurrentUser, DbSession
from app.models import Account
from app.schemas import MAX_DB_ID, AccountCreate, AccountOut, BalanceOut, DepositRequest, ErrorOut, HistoryEntry

AccountId = Annotated[int, Path(gt=0, le=MAX_DB_ID)]

router = APIRouter(prefix="/api/accounts", tags=["accounts"], responses={401: {"model": ErrorOut}})


@router.post("", status_code=201, response_model=AccountOut)
def create_account(body: AccountCreate, user: CurrentUser, db: DbSession) -> Account:
    account = Account(owner_id=user.id, currency=body.currency)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("", response_model=list[AccountOut])
def list_accounts(user: CurrentUser, db: DbSession) -> list[Account]:
    return list(db.scalars(select(Account).where(Account.owner_id == user.id).order_by(Account.id)))


@router.get("/{account_id}", response_model=AccountOut, responses={404: {"model": ErrorOut}})
def get_account(account_id: AccountId, user: CurrentUser, db: DbSession) -> Account:
    return services.get_own_account(db, user, account_id)


@router.get("/{account_id}/balance", response_model=BalanceOut, responses={404: {"model": ErrorOut}})
def get_balance(account_id: AccountId, user: CurrentUser, db: DbSession) -> BalanceOut:
    account = services.get_own_account(db, user, account_id)
    return BalanceOut(account_id=account.id, currency=account.currency, balance=account.balance)


@router.post("/{account_id}/deposit", response_model=AccountOut, responses={404: {"model": ErrorOut}})
def deposit(account_id: AccountId, body: DepositRequest, user: CurrentUser, db: DbSession) -> Account:
    return services.deposit(db, user, account_id, body.amount)


@router.get("/{account_id}/transactions", response_model=list[HistoryEntry], responses={404: {"model": ErrorOut}})
def history(
    account_id: AccountId,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[HistoryEntry]:
    account = services.get_own_account(db, user, account_id)
    entries = []
    for tx in services.account_history(db, account.id, limit, offset):
        incoming = tx.to_account_id == account.id
        entries.append(
            HistoryEntry(
                id=tx.id,
                type=tx.type,
                direction="CREDIT" if incoming else "DEBIT",
                amount=tx.amount,
                counterparty_account_id=tx.from_account_id if incoming else tx.to_account_id,
                description=tx.description,
                created_at=tx.created_at,
            )
        )
    return entries
