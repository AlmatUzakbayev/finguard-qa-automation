"""Idempotency and parallel requests.

How these tests stay reproducible:
- a threading.Barrier releases all threads at the same moment, which maximises
  overlap without any sleep();
- assertions are about invariants that must hold for EVERY possible interleaving
  ("exactly 3 of 10 succeed", "balance debited once"), never about which request
  happens to win. A correct server passes every time, a server with a race fails
  with high probability, and no timing tuning is needed.
"""

import threading
import uuid
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import httpx
import pytest

from tests.support.api_client import FinGuardApi
from tests.support.assertions import assert_error, assert_status


def run_in_parallel(base_url: str, token: str, count: int, call: Callable[[FinGuardApi, int], httpx.Response]):
    """Run `call(api, index)` in `count` threads that all start at the same instant."""
    barrier = threading.Barrier(count)

    def worker(index: int) -> httpx.Response:
        api = FinGuardApi(base_url, token)  # one HTTP client per thread
        try:
            barrier.wait(timeout=10)
            return call(api, index)
        finally:
            api.close()

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(worker, range(count)))


@pytest.mark.functional
def test_retry_with_same_idempotency_key_returns_original_transfer(user, account_factory, db):
    source = account_factory(user, balance="100.00")
    target = account_factory(user)
    key = str(uuid.uuid4())

    first = user.api.transfer(source["id"], target["id"], "25.00", key=key)
    retry = user.api.transfer(source["id"], target["id"], "25.00", key=key)

    assert_status(first, 201)
    assert_status(retry, 200)
    assert retry.json() == first.json(), "A replay must return the original transfer unchanged"
    assert retry.headers.get("Idempotent-Replayed") == "true"
    assert db.balance(source["id"]) == Decimal("75.00"), "Money must be debited only once"
    assert len(db.transfers_between(source["id"], target["id"])) == 1


@pytest.mark.negative
def test_reusing_idempotency_key_with_different_body_is_a_conflict(user, account_factory, db):
    source = account_factory(user, balance="100.00")
    target = account_factory(user)
    key = str(uuid.uuid4())
    assert_status(user.api.transfer(source["id"], target["id"], "25.00", key=key), 201)

    response = user.api.transfer(source["id"], target["id"], "26.00", key=key)

    assert_error(response, 409, "IDEMPOTENCY_KEY_REUSED")
    assert db.balance(source["id"]) == Decimal("75.00")


@pytest.mark.functional
def test_idempotency_keys_are_scoped_per_user(user, other_user, account_factory):
    """Two different customers may accidentally generate the same key; that must not
    turn the second customer's transfer into a replay of the first one's."""
    key = "shared-key-" + uuid.uuid4().hex
    a1, a2 = account_factory(user, balance="10.00"), account_factory(user)
    b1, b2 = account_factory(other_user, balance="10.00"), account_factory(other_user)

    assert_status(user.api.transfer(a1["id"], a2["id"], "1.00", key=key), 201)
    assert_status(other_user.api.transfer(b1["id"], b2["id"], "1.00", key=key), 201)


@pytest.mark.concurrency
def test_parallel_retries_with_same_key_debit_only_once(base_url, user, account_factory, db):
    """A client that retries aggressively (10 identical requests at once) is charged once."""
    source = account_factory(user, balance="100.00")
    target = account_factory(user)
    key = str(uuid.uuid4())

    responses = run_in_parallel(
        base_url, user.token, 10, lambda api, _: api.transfer(source["id"], target["id"], "40.00", key=key)
    )

    statuses = Counter(r.status_code for r in responses)
    assert statuses == {201: 1, 200: 9}, f"Expected one 201 and nine replays (200), got {dict(statuses)}"
    assert len({r.json()["id"] for r in responses}) == 1, "All responses must describe the same transfer"
    assert db.balance(source["id"]) == Decimal("60.00")
    assert db.balance(target["id"]) == Decimal("40.00")
    assert len(db.transfers_between(source["id"], target["id"])) == 1


@pytest.mark.concurrency
def test_parallel_transfers_never_overdraw_the_account(base_url, user, account_factory, db):
    """10 different transfers of 30.00 race for a balance of 100.00. Whatever the order,
    exactly 3 can succeed and the balance must never go below zero."""
    source = account_factory(user, balance="100.00")
    target = account_factory(user)

    responses = run_in_parallel(
        base_url, user.token, 10, lambda api, _: api.transfer(source["id"], target["id"], "30.00")
    )

    statuses = Counter(r.status_code for r in responses)
    assert statuses == {201: 3, 422: 7}, f"Expected 3 successes and 7 rejections, got {dict(statuses)}"
    assert all(r.json()["code"] == "INSUFFICIENT_FUNDS" for r in responses if r.status_code == 422)
    assert db.balance(source["id"]) == Decimal("10.00")
    assert db.balance(target["id"]) == Decimal("90.00")
    assert len(db.transfers_between(source["id"], target["id"])) == 3


@pytest.mark.concurrency
def test_opposite_parallel_transfers_do_not_deadlock_or_lose_money(base_url, user, account_factory, db):
    """A->B and B->A at the same time is the classic deadlock scenario. The server
    locks accounts in a fixed order, so every request must complete normally."""
    a = account_factory(user, balance="100.00")
    b = account_factory(user, balance="100.00")

    def call(api: FinGuardApi, index: int) -> httpx.Response:
        if index % 2 == 0:
            return api.transfer(a["id"], b["id"], "1.00")
        return api.transfer(b["id"], a["id"], "1.00")

    responses = run_in_parallel(base_url, user.token, 20, call)

    assert [r.status_code for r in responses] == [201] * 20, [r.text for r in responses if r.status_code != 201]
    assert db.balance(a["id"]) == Decimal("100.00")  # 10 out, 10 in
    assert db.balance(b["id"]) == Decimal("100.00")
