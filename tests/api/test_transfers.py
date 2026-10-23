"""Money transfers: the happy path, history, and everything that must be refused."""

from decimal import Decimal

import pytest

from tests.support.assertions import assert_error, assert_status


@pytest.mark.smoke
@pytest.mark.functional
def test_transfer_moves_money_between_users(user, other_user, account_factory):
    source = account_factory(user, balance="1000.00")
    target = account_factory(other_user)

    response = user.api.transfer(source["id"], target["id"], "250.50", description="Rent for October")

    assert_status(response, 201)
    transfer = response.json()
    assert transfer["from_account_id"] == source["id"]
    assert transfer["to_account_id"] == target["id"]
    assert transfer["amount"] == "250.50"
    assert transfer["description"] == "Rent for October"
    assert user.api.get_balance(source["id"]).json()["balance"] == "749.50"
    assert other_user.api.get_balance(target["id"]).json()["balance"] == "250.50"


@pytest.mark.functional
def test_history_shows_debit_for_sender_and_credit_for_receiver(user, other_user, account_factory):
    source = account_factory(user, balance="100.00")
    target = account_factory(other_user)
    transfer_id = user.api.transfer(source["id"], target["id"], "40.00", description="Lunch").json()["id"]

    sender_history = user.api.history(source["id"]).json()
    receiver_history = other_user.api.history(target["id"]).json()

    # Newest first: the transfer, then the initial deposit.
    assert [(e["type"], e["direction"], e["amount"]) for e in sender_history] == [
        ("TRANSFER", "DEBIT", "40.00"),
        ("DEPOSIT", "CREDIT", "100.00"),
    ]
    assert sender_history[0]["id"] == transfer_id
    assert sender_history[0]["counterparty_account_id"] == target["id"]
    assert len(receiver_history) == 1
    entry = receiver_history[0]
    entry.pop("created_at")
    assert entry == {
        "id": transfer_id,
        "type": "TRANSFER",
        "direction": "CREDIT",
        "amount": "40.00",
        "counterparty_account_id": source["id"],
        "description": "Lunch",
    }


@pytest.mark.functional
def test_history_pagination(user, account_factory):
    account = account_factory(user)
    for amount in ("1.00", "2.00", "3.00"):
        assert_status(user.api.deposit(account["id"], amount), 200)

    page = user.api.history(account["id"], limit=2, offset=1)

    assert_status(page, 200)
    assert [e["amount"] for e in page.json()] == ["2.00", "1.00"]


@pytest.mark.negative
@pytest.mark.parametrize(
    "amount",
    [
        pytest.param("-10.00", id="negative"),
        pytest.param("0", id="zero"),
        pytest.param("0.00", id="zero-with-decimals"),
        pytest.param("0.001", id="three-decimals"),
        pytest.param("abc", id="not-a-number"),
        pytest.param("NaN", id="nan"),
        pytest.param(None, id="null"),
    ],
)
def test_transfer_with_invalid_amount_is_rejected_and_changes_nothing(user, account_factory, db, amount):
    source = account_factory(user, balance="100.00")
    target = account_factory(user)

    response = user.api.transfer(source["id"], target["id"], amount)

    body = assert_error(response, 422, "VALIDATION_ERROR")
    assert ["body", "amount"] in [e["loc"][:2] for e in body["errors"]]
    assert db.balance(source["id"]) == Decimal("100.00")
    assert db.transfers_between(source["id"], target["id"]) == []


@pytest.mark.negative
def test_transfer_with_insufficient_funds_is_rejected_and_changes_nothing(user, other_user, account_factory):
    source = account_factory(user, balance="50.00")
    target = account_factory(other_user, balance="10.00")

    response = user.api.transfer(source["id"], target["id"], "50.01")

    assert_error(response, 422, "INSUFFICIENT_FUNDS")
    assert user.api.get_balance(source["id"]).json()["balance"] == "50.00"
    assert other_user.api.get_balance(target["id"]).json()["balance"] == "10.00"


@pytest.mark.negative
def test_cannot_transfer_from_someone_elses_account(user, other_user, account_factory):
    victim_account = account_factory(other_user, balance="1000.00")
    attacker_account = account_factory(user)

    response = user.api.transfer(victim_account["id"], attacker_account["id"], "999.00")

    body = assert_error(response, 404, "NOT_FOUND")
    assert body["detail"] == "Source account not found"
    assert other_user.api.get_balance(victim_account["id"]).json()["balance"] == "1000.00"
    assert user.api.get_balance(attacker_account["id"]).json()["balance"] == "0.00"


@pytest.mark.negative
def test_transfer_to_nonexistent_account_returns_404(user, account_factory):
    source = account_factory(user, balance="100.00")

    response = user.api.transfer(source["id"], 2_000_000_000, "10.00")

    body = assert_error(response, 404, "NOT_FOUND")
    assert body["detail"] == "Destination account not found"
    assert user.api.get_balance(source["id"]).json()["balance"] == "100.00"


@pytest.mark.negative
def test_transfer_to_out_of_range_account_id_is_rejected(user, account_factory):
    """Regression test for BUG-001 (the request body variant): HTTP 500 before the fix."""
    source = account_factory(user, balance="100.00")

    body = assert_error(user.api.transfer(source["id"], 99_999_999_999, "10.00"), 422, "VALIDATION_ERROR")
    assert body["errors"][0]["loc"] == ["body", "to_account_id"]


@pytest.mark.negative
def test_transfer_to_the_same_account_is_rejected(user, account_factory):
    account = account_factory(user, balance="100.00")

    assert_error(user.api.transfer(account["id"], account["id"], "10.00"), 422, "VALIDATION_ERROR")


@pytest.mark.negative
def test_transfer_between_different_currencies_is_rejected(user, account_factory):
    kzt = account_factory(user, balance="100.00", currency="KZT")
    usd = account_factory(user, currency="USD")

    assert_error(user.api.transfer(kzt["id"], usd["id"], "10.00"), 422, "CURRENCY_MISMATCH")
    assert user.api.get_balance(kzt["id"]).json()["balance"] == "100.00"


@pytest.mark.negative
def test_transfer_without_idempotency_key_is_rejected(user, account_factory):
    source = account_factory(user, balance="100.00")
    target = account_factory(user)
    body = {"from_account_id": source["id"], "to_account_id": target["id"], "amount": "10.00"}

    response = user.api.http.post("/api/transfers", json=body, headers=user.api._headers())

    body = assert_error(response, 422, "VALIDATION_ERROR")
    assert ["header", "Idempotency-Key"] in [e["loc"] for e in body["errors"]]
