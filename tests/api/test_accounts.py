"""Accounts, balances and access control (BOLA / IDOR checks)."""

import pytest

from tests.support.assertions import assert_error, assert_status


@pytest.mark.smoke
@pytest.mark.functional
@pytest.mark.parametrize(("currency", "expected"), [(None, "KZT"), ("USD", "USD"), ("EUR", "EUR")])
def test_create_account_starts_with_zero_balance(user, currency, expected):
    response = user.api.create_account(currency)

    assert_status(response, 201)
    body = response.json()
    assert body["currency"] == expected
    assert body["balance"] == "0.00"


@pytest.mark.negative
@pytest.mark.parametrize("currency", ["RUB", "kzt", "", "KZTT"])
def test_create_account_with_unsupported_currency_returns_422(user, currency):
    assert_error(user.api.create_account(currency), 422, "VALIDATION_ERROR")


@pytest.mark.functional
def test_deposit_increases_balance(user, account_factory):
    account = account_factory(user)

    assert_status(user.api.deposit(account["id"], "150.25"), 200)
    assert_status(user.api.deposit(account["id"], "49.75"), 200)

    balance = user.api.get_balance(account["id"])
    assert_status(balance, 200)
    assert balance.json() == {"account_id": account["id"], "currency": "KZT", "balance": "200.00"}


@pytest.mark.negative
def test_account_list_contains_only_own_accounts(user, other_user, account_factory):
    mine = {account_factory(user)["id"], account_factory(user)["id"]}
    foreign = account_factory(other_user)["id"]

    response = user.api.list_accounts()

    assert_status(response, 200)
    listed = {a["id"] for a in response.json()}
    assert listed == mine, f"Expected exactly own accounts {mine}, got {listed}"
    assert foreign not in listed


@pytest.mark.negative
@pytest.mark.parametrize("action", ["get_account", "get_balance", "history", "deposit"])
def test_foreign_account_is_indistinguishable_from_missing_one(user, other_user, account_factory, action):
    """Another user's account must answer exactly like a non-existent one (404), so an
    attacker cannot even confirm that an account id exists."""
    foreign_id = account_factory(other_user, balance="500.00")["id"]

    def call(account_id):
        method = getattr(user.api, action)
        return method(account_id, "1.00") if action == "deposit" else method(account_id)

    foreign = call(foreign_id)
    missing = call(2_000_000_000)

    assert_error(foreign, 404, "NOT_FOUND")
    assert foreign.json() == missing.json()
    # And nothing changed on the victim's side.
    assert other_user.api.get_balance(foreign_id).json()["balance"] == "500.00"


@pytest.mark.negative
@pytest.mark.parametrize(
    "account_id",
    [
        pytest.param("0", id="zero"),
        pytest.param("-1", id="negative"),
        pytest.param("2147483648", id="int32-max-plus-1"),
        pytest.param("99999999999999999999", id="huge"),
        pytest.param("abc", id="not-a-number"),
    ],
)
def test_invalid_account_id_is_rejected_by_validation(user, account_id):
    """Regression test for BUG-001: ids above the PostgreSQL INTEGER range caused HTTP 500."""
    response = user.api.get_account(account_id)

    assert_error(response, 422, "VALIDATION_ERROR")
