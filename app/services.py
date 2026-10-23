"""Money-moving business logic.

How a transfer stays correct under concurrency:
1. Both account rows are locked with SELECT ... FOR UPDATE, always in ascending id
   order. Concurrent transfers touching the same accounts therefore run one after
   another, and two opposite transfers (A->B and B->A) cannot deadlock.
2. The idempotency key is checked *after* the locks are taken, so a retried request
   waits for the original one and then sees its committed result.
3. Balance updates and the transaction record are committed together in one database
   transaction: either everything is saved or nothing is.
4. The database has the last word: CHECK (balance >= 0) and a UNIQUE idempotency key.
"""

import hashlib
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError, not_found
from app.models import Account, Transaction, User
from app.schemas import TransferRequest


def _request_hash(req: TransferRequest) -> str:
    raw = f"{req.from_account_id}|{req.to_account_id}|{req.amount}|{req.description or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _find_by_key(db: Session, user: User, key: str) -> Transaction | None:
    return db.scalar(select(Transaction).where(Transaction.initiator_id == user.id, Transaction.idempotency_key == key))


def _replay(existing: Transaction, request_hash: str) -> tuple[Transaction, bool]:
    if existing.request_hash != request_hash:
        raise AppError(
            409,
            "IDEMPOTENCY_KEY_REUSED",
            "This Idempotency-Key was already used with a different request body",
        )
    return existing, True


def _record_transfer(db: Session, user: User, req: TransferRequest, key: str, request_hash: str) -> Transaction:
    tx = Transaction(
        type="TRANSFER",
        from_account_id=req.from_account_id,
        to_account_id=req.to_account_id,
        amount=req.amount,
        description=req.description,
        initiator_id=user.id,
        idempotency_key=key,
        request_hash=request_hash,
    )
    db.add(tx)
    db.flush()
    return tx


def execute_transfer(db: Session, user: User, req: TransferRequest, key: str) -> tuple[Transaction, bool]:
    """Move money between two accounts. Returns (transaction, replayed)."""
    request_hash = _request_hash(req)

    locked = db.scalars(
        select(Account)
        .where(Account.id.in_([req.from_account_id, req.to_account_id]))
        .order_by(Account.id)
        .with_for_update()
    ).all()
    accounts = {a.id: a for a in locked}

    existing = _find_by_key(db, user, key)
    if existing is not None:
        db.rollback()
        return _replay(existing, request_hash)

    source = accounts.get(req.from_account_id)
    target = accounts.get(req.to_account_id)
    # Someone else's account is reported as "not found" rather than "forbidden",
    # so the API does not reveal which account ids exist.
    if source is None or source.owner_id != user.id:
        raise not_found("Source account")
    if target is None:
        raise not_found("Destination account")
    if source.currency != target.currency:
        raise AppError(422, "CURRENCY_MISMATCH", "Accounts must have the same currency")
    if source.balance < req.amount:
        raise AppError(422, "INSUFFICIENT_FUNDS", "Insufficient funds on the source account")

    source.balance -= req.amount
    target.balance += req.amount
    db.flush()  # the UPDATE statements are sent now, but not committed yet
    tx = _record_transfer(db, user, req, key, request_hash)

    try:
        db.commit()
    except IntegrityError:
        # Lost a race on the same idempotency key with a different body: the other
        # request committed first. Nothing of ours was saved.
        db.rollback()
        existing = _find_by_key(db, user, key)
        if existing is None:
            raise
        return _replay(existing, request_hash)
    return tx, False


def deposit(db: Session, user: User, account_id: int, amount: Decimal) -> Account:
    """Top up an account. A training-only feature: in a real bank money comes from outside."""
    account = db.scalar(select(Account).where(Account.id == account_id).with_for_update())
    if account is None or account.owner_id != user.id:
        raise not_found("Account")
    account.balance += amount
    db.add(Transaction(type="DEPOSIT", to_account_id=account.id, amount=amount, initiator_id=user.id))
    db.commit()
    return account


def get_own_account(db: Session, user: User, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None or account.owner_id != user.id:
        raise not_found("Account")
    return account


def account_history(db: Session, account_id: int, limit: int, offset: int) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(or_(Transaction.from_account_id == account_id, Transaction.to_account_id == account_id))
            .order_by(Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
