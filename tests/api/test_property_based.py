"""Property-based tests: Hypothesis generates the inputs instead of us.

1. Fuzzing of the amount field: whatever a client sends as "amount", the API
   answers with a validation error or a success, never with HTTP 500, and it
   never accepts an amount outside the business rules.
2. A stateful (model-based) test: Hypothesis runs random sequences of deposits,
   transfers and retried transfers, and after every step compares the API and
   the database with a simple in-memory model of the bank.

Hypothesis shrinks a failing case to the shortest sequence that still fails,
so a red test comes with a minimal reproduction.

Fixtures used inside @given / state machines must not be function-scoped
(Hypothesis runs many examples per test call), so these tests build their
users directly with FinGuardApi on top of the session-scoped base_url.
"""

import uuid
from decimal import Decimal, InvalidOperation

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule, run_state_machine_as_test

from tests.conftest import DEFAULT_PASSWORD, unique_email
from tests.support.api_client import FinGuardApi
from tests.support.assertions import assert_error, assert_status

pytestmark = pytest.mark.property

MIN_AMOUNT = Decimal("0.01")
MAX_AMOUNT = Decimal("1000000.00")

# Every value a client could put into the JSON "amount" field.
ANY_JSON_AMOUNT = st.one_of(
    st.decimals(allow_nan=True, allow_infinity=True).map(str),
    st.decimals(min_value=-10, max_value=2_000_000, places=3).map(str),
    st.integers(min_value=-(10**20), max_value=10**20),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=20),
    st.none(),
    st.booleans(),
    st.lists(st.integers(), max_size=2),
)

VALID_DEPOSIT = st.decimals(min_value=MIN_AMOUNT, max_value=Decimal("5000.00"), places=2)
# Transfer amounts are drawn as a share of the current balance: purely random amounts
# almost never produce a large successful transfer, so bugs that only show up on big
# amounts went unnoticed. Shares above 100% exercise INSUFFICIENT_FUNDS.
BALANCE_SHARE_PERCENT = st.integers(min_value=1, max_value=120)


def new_user_api(base_url: str) -> FinGuardApi:
    api = FinGuardApi(base_url)
    email = unique_email("prop")
    assert_status(api.register(email, DEFAULT_PASSWORD, "Property Test"), 201)
    login = api.login(email, DEFAULT_PASSWORD)
    assert_status(login, 200)
    api.token = login.json()["access_token"]
    return api


def is_allowed_amount(value) -> bool:
    """The business rule for an accepted amount: 0.01 .. 1 000 000.00 with at most 2 decimals."""
    if isinstance(value, bool) or value is None or isinstance(value, list):
        return False
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return False
    if not amount.is_finite():
        return False
    return MIN_AMOUNT <= amount <= MAX_AMOUNT and amount == amount.quantize(Decimal("0.01"))


@pytest.fixture(scope="module")
def fuzz_account(base_url):
    api = new_user_api(base_url)
    created = api.create_account("KZT")
    assert_status(created, 201)
    yield api, created.json()["id"]
    api.close()


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(amount=ANY_JSON_AMOUNT)
def test_deposit_amount_fuzzing_never_breaks_the_api(fuzz_account, amount):
    api, account_id = fuzz_account
    before = Decimal(api.get_balance(account_id).json()["balance"])

    response = api.http.post(f"/api/accounts/{account_id}/deposit", json={"amount": amount}, headers=api._headers())

    assert response.status_code in (200, 422), f"amount={amount!r} -> HTTP {response.status_code}: {response.text}"
    after = Decimal(api.get_balance(account_id).json()["balance"])
    if response.status_code == 200:
        assert is_allowed_amount(amount), f"API accepted an amount that breaks the rules: {amount!r}"
        assert after == before + Decimal(str(amount))
    else:
        assert_error(response, 422, "VALIDATION_ERROR")
        assert after == before, f"A rejected deposit changed the balance: {amount!r}"


class BankModel(RuleBasedStateMachine):
    """One customer with three KZT accounts; the model is a dict of expected balances."""

    base_url: str
    db = None

    def __init__(self):
        super().__init__()
        self.api = new_user_api(self.base_url)
        self.accounts: list[int] = []
        for _ in range(3):
            created = self.api.create_account("KZT")
            assert_status(created, 201)
            self.accounts.append(created.json()["id"])
        self.expected = {account_id: Decimal("0.00") for account_id in self.accounts}
        self.total_deposited = Decimal("0.00")

    def teardown(self):
        self.api.close()

    @rule(index=st.integers(0, 2), amount=VALID_DEPOSIT)
    def deposit(self, index, amount):
        account_id = self.accounts[index]
        assert_status(self.api.deposit(account_id, amount), 200)
        self.expected[account_id] += amount
        self.total_deposited += amount

    def amount_for(self, account_id: int, percent: int) -> Decimal:
        amount = (self.expected[account_id] * percent / 100).quantize(Decimal("0.01"))
        return max(amount, MIN_AMOUNT)

    @rule(src=st.integers(0, 2), dst=st.integers(0, 2), percent=BALANCE_SHARE_PERCENT)
    def transfer(self, src, dst, percent):
        from_id, to_id = self.accounts[src], self.accounts[dst]
        amount = self.amount_for(from_id, percent)
        response = self.api.transfer(from_id, to_id, amount)
        if from_id == to_id:
            assert_error(response, 422, "VALIDATION_ERROR")
        elif amount > self.expected[from_id]:
            assert_error(response, 422, "INSUFFICIENT_FUNDS")
        else:
            assert_status(response, 201)
            self.expected[from_id] -= amount
            self.expected[to_id] += amount

    @rule(percent=st.integers(min_value=1, max_value=100))
    def retried_transfer_is_charged_once(self, percent):
        from_id, to_id = self.accounts[0], self.accounts[1]
        amount = self.amount_for(from_id, percent)
        if amount > self.expected[from_id]:
            return
        key = str(uuid.uuid4())
        first = self.api.transfer(from_id, to_id, amount, key=key)
        retry = self.api.transfer(from_id, to_id, amount, key=key)
        assert_status(first, 201)
        assert_status(retry, 200)
        assert retry.json()["id"] == first.json()["id"]
        self.expected[from_id] -= amount
        self.expected[to_id] += amount

    @invariant()
    def api_balances_match_the_model(self):
        for account_id, expected in self.expected.items():
            assert Decimal(self.api.get_balance(account_id).json()["balance"]) == expected

    @invariant()
    def database_ledger_is_consistent(self):
        for account_id in self.accounts:
            assert self.db.balance(account_id) >= 0
            assert self.db.balance(account_id) == self.db.ledger_balance(account_id)

    @invariant()
    def money_is_neither_created_nor_lost(self):
        assert sum(self.db.balance(a) for a in self.accounts) == self.total_deposited


def test_random_operation_sequences_keep_the_bank_consistent(base_url, db):
    BankModel.base_url = base_url
    BankModel.db = db
    run_state_machine_as_test(
        BankModel,
        settings=settings(
            max_examples=20,
            stateful_step_count=15,
            deadline=None,
            suppress_health_check=[HealthCheck.too_slow],
        ),
    )
