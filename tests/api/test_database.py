"""Checks made directly against PostgreSQL.

The API can say "201 Created" and still store the wrong thing; these tests look
at what was actually persisted, and at what must NOT have been persisted.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import services
from app.models import User
from app.schemas import TransferRequest
from tests.support.assertions import assert_error, assert_status


@pytest.mark.db
def test_transfer_is_persisted_exactly(user, other_user, account_factory, db):
    source = account_factory(user, balance="500.00")
    target = account_factory(other_user)

    response = user.api.transfer(source["id"], target["id"], "123.45", key="db-check-1")
    assert_status(response, 201)

    assert db.balance(source["id"]) == Decimal("376.55")
    assert db.balance(target["id"]) == Decimal("123.45")
    rows = db.transfers_between(source["id"], target["id"])
    assert len(rows) == 1, f"Expected exactly one transaction row, got {rows}"
    row = rows[0]
    assert row["id"] == response.json()["id"]
    assert row["amount"] == Decimal("123.45")  # NUMERIC -> Decimal, no float rounding
    assert row["initiator_id"] == user.id
    assert row["idempotency_key"] == "db-check-1"


@pytest.mark.db
def test_rejected_transfer_leaves_no_trace_in_database(user, other_user, account_factory, db):
    source = account_factory(user, balance="10.00")
    target = account_factory(other_user)
    rows_before = db.count_transactions(source["id"])

    assert_error(user.api.transfer(source["id"], target["id"], "10.01"), 422, "INSUFFICIENT_FUNDS")

    assert db.balance(source["id"]) == Decimal("10.00")
    assert db.balance(target["id"]) == Decimal("0.00")
    assert db.count_transactions(source["id"]) == rows_before
    assert db.count_transactions(target["id"]) == 0


@pytest.mark.db
def test_transfer_is_rolled_back_completely_if_it_fails_midway(user, account_factory, db, db_engine, monkeypatch):
    """White-box atomicity test: simulate a crash *after* the balances were updated
    but *before* the transaction record was written, and check that the debit did
    not survive on its own."""
    source = account_factory(user, balance="100.00")
    target = account_factory(user)
    seen_inside_transaction = {}

    def crash_while_recording(session, *args, **kwargs):
        # Inside the still-open DB transaction the debit is already applied...
        seen_inside_transaction["balance"] = session.execute(
            text("SELECT balance FROM accounts WHERE id = :id"), {"id": source["id"]}
        ).scalar_one()
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(services, "_record_transfer", crash_while_recording)
    request = TransferRequest(from_account_id=source["id"], to_account_id=target["id"], amount=Decimal("30.00"))

    with Session(db_engine) as session, pytest.raises(RuntimeError, match="simulated crash"):
        services.execute_transfer(session, session.get(User, user.id), request, "atomicity-key")

    assert seen_inside_transaction["balance"] == Decimal("70.00"), "the crash must happen after the debit"
    # ...but after the failure nothing is committed.
    assert db.balance(source["id"]) == Decimal("100.00")
    assert db.balance(target["id"]) == Decimal("0.00")
    assert db.transfers_between(source["id"], target["id"]) == []


@pytest.mark.db
@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        pytest.param(
            "UPDATE accounts SET balance = -0.01 WHERE id = :a",
            "ck_accounts_balance_non_negative",
            id="negative-balance",
        ),
        pytest.param(
            "INSERT INTO transactions (type, to_account_id, amount, initiator_id) VALUES ('DEPOSIT', :a, 0, :u)",
            "ck_transactions_amount_positive",
            id="zero-amount",
        ),
        pytest.param(
            "INSERT INTO transactions (type, from_account_id, to_account_id, amount, initiator_id) "
            "VALUES ('TRANSFER', :a, :a, 1, :u)",
            "ck_transactions_different_accounts",
            id="self-transfer",
        ),
    ],
)
def test_database_constraints_protect_invariants(user, account_factory, db_engine, statement, constraint):
    """Even if application code had a bug, the database itself refuses invalid data."""
    account = account_factory(user, balance="1.00")

    with pytest.raises(IntegrityError, match=constraint), db_engine.begin() as conn:
        conn.execute(text(statement), {"a": account["id"], "u": user.id})


@pytest.mark.db
def test_balances_reconcile_with_transaction_ledger(user, other_user, account_factory, db):
    """After a mix of successful and failed operations, every balance must equal
    credits minus debits from the transaction log, and no money may appear or vanish."""
    a = account_factory(user, balance="300.00")
    b = account_factory(user, balance="50.00")
    c = account_factory(other_user, balance="0.00")
    accounts = [a["id"], b["id"], c["id"]]
    total_before = sum(db.balance(acc) for acc in accounts)

    user.api.transfer(a["id"], b["id"], "120.00")
    user.api.transfer(b["id"], c["id"], "170.00")
    user.api.transfer(b["id"], c["id"], "0.01")  # fails: b is empty now
    other_user.api.transfer(c["id"], a["id"], "70.00")
    user.api.transfer(a["id"], c["id"], "250.01")  # fails: a has 250.00

    for acc in accounts:
        assert db.balance(acc) == db.ledger_balance(acc), f"Account {acc}: balance does not match ledger"
    assert sum(db.balance(acc) for acc in accounts) == total_before
    assert [db.balance(acc) for acc in accounts] == [Decimal("250.00"), Decimal("0.00"), Decimal("100.00")]
