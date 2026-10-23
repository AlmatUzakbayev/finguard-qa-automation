"""Contract tests: HTTP status codes and the exact JSON structure of responses."""

import pytest
from pydantic import TypeAdapter, ValidationError

from tests.conftest import unique_email
from tests.support.assertions import assert_status
from tests.support.contracts import (
    AccountContract,
    BalanceContract,
    ErrorContract,
    HistoryEntryContract,
    TokenContract,
    TransferContract,
    UserContract,
)


def assert_matches(contract, response) -> None:
    try:
        TypeAdapter(contract).validate_python(response.json())
    except ValidationError as exc:
        pytest.fail(f"{response.request.method} {response.request.url.path} breaks the contract:\n{exc}")


@pytest.mark.contract
def test_successful_responses_match_contract(anon_api, user, other_user, account_factory):
    """Walk through the main flow and validate every response body and status code."""
    email = unique_email()
    register = anon_api.register(email, "Str0ng-Passw0rd!", "Contract User")
    assert_status(register, 201)
    assert_matches(UserContract, register)

    login = anon_api.login(email, "Str0ng-Passw0rd!")
    assert_status(login, 200)
    assert_matches(TokenContract, login)

    created = user.api.create_account()
    assert_status(created, 201)
    assert_matches(AccountContract, created)
    account_id = created.json()["id"]

    deposit = user.api.deposit(account_id, "100")
    assert_status(deposit, 200)
    assert_matches(AccountContract, deposit)
    assert deposit.json()["balance"] == "100.00", "Money must always be rendered with two decimals"

    target = account_factory(other_user)
    transfer = user.api.transfer(account_id, target["id"], "12.5")
    assert_status(transfer, 201)
    assert_matches(TransferContract, transfer)
    assert transfer.json()["amount"] == "12.50"

    for response, contract in [
        (user.api.me(), UserContract),
        (user.api.list_accounts(), list[AccountContract]),
        (user.api.get_account(account_id), AccountContract),
        (user.api.get_balance(account_id), BalanceContract),
        (user.api.history(account_id), list[HistoryEntryContract]),
    ]:
        assert_status(response, 200)
        assert_matches(contract, response)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("scenario", "expected_status"),
    [("unauthorized", 401), ("not_found", 404), ("conflict", 409), ("validation", 422)],
)
def test_error_responses_share_one_format(anon_api, user, scenario, expected_status):
    calls = {
        "unauthorized": lambda: anon_api.list_accounts(),
        "not_found": lambda: user.api.get_account(2_000_000_000),
        "conflict": lambda: anon_api.register(user.email, "Str0ng-Passw0rd!", "Duplicate"),
        "validation": lambda: user.api.create_account("XXX"),
    }

    response = calls[scenario]()

    assert_status(response, expected_status)
    assert response.headers["content-type"] == "application/json"
    assert_matches(ErrorContract, response)


@pytest.mark.contract
def test_openapi_schema_is_published(anon_api):
    response = anon_api.http.get("/openapi.json")

    assert_status(response, 200)
    paths = response.json()["paths"]
    for path in ["/api/auth/register", "/api/auth/login", "/api/transfers", "/api/accounts/{account_id}/balance"]:
        assert path in paths, f"{path} is missing from the OpenAPI schema"
