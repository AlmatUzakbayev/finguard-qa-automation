"""Boundary value analysis: each limit is tested on, just below and just above the edge.

Business limits (see app/config.py):
- minimum amount:            0.01
- maximum single transfer:   1 000 000.00
- maximum single deposit:    1 000 000.00
- password length:           8..128 characters
"""

import pytest

from tests.conftest import unique_email
from tests.support.assertions import assert_error, assert_status


@pytest.mark.boundary
@pytest.mark.parametrize(
    ("balance", "amount", "expected_status", "expected_balance_after"),
    [
        pytest.param("100.00", "0.01", 201, "99.99", id="minimum-amount"),
        pytest.param("100.00", "100.00", 201, "0.00", id="amount-equals-balance"),
        pytest.param("100.00", "100.01", 422, "100.00", id="balance-plus-one-cent"),
        pytest.param("1000000.00", "1000000.00", 201, "0.00", id="maximum-amount"),
        pytest.param("1000000.00", "1000000.01", 422, "1000000.00", id="maximum-plus-one-cent"),
    ],
)
def test_transfer_amount_boundaries(user, account_factory, balance, amount, expected_status, expected_balance_after):
    source = account_factory(user, balance=balance)
    target = account_factory(user)

    response = user.api.transfer(source["id"], target["id"], amount)

    assert_status(response, expected_status)
    assert user.api.get_balance(source["id"]).json()["balance"] == expected_balance_after


@pytest.mark.boundary
def test_over_limit_transfer_fails_validation_even_with_enough_money(user, account_factory):
    """1 000 000.01 is refused because of the per-transfer limit, not because of the balance."""
    source = account_factory(user, balance="1000000.00")
    assert_status(user.api.deposit(source["id"], "1000000.00"), 200)  # balance is now 2 000 000.00
    target = account_factory(user)

    body = assert_error(user.api.transfer(source["id"], target["id"], "1000000.01"), 422, "VALIDATION_ERROR")
    assert body["errors"][0]["type"] == "less_than_equal"


@pytest.mark.boundary
@pytest.mark.parametrize(
    ("amount", "expected_status"),
    [
        pytest.param("0.00", 422, id="zero"),
        pytest.param("0.01", 200, id="minimum"),
        pytest.param("1000000.00", 200, id="maximum"),
        pytest.param("1000000.01", 422, id="maximum-plus-one-cent"),
    ],
)
def test_deposit_amount_boundaries(user, account_factory, amount, expected_status):
    account = account_factory(user)

    assert_status(user.api.deposit(account["id"], amount), expected_status)


@pytest.mark.boundary
@pytest.mark.parametrize(
    ("length", "expected_status"),
    [(7, 422), (8, 201), (128, 201), (129, 422)],
    ids=["7-too-short", "8-minimum", "128-maximum", "129-too-long"],
)
def test_password_length_boundaries(anon_api, length, expected_status):
    response = anon_api.register(unique_email(), "p" * length, "Boundary User")

    assert_status(response, expected_status)
