"""Load test: many customers checking balances, reading history and making transfers.

Run against a running server, for example:
    locust -f tests/load/locustfile.py --host http://127.0.0.1:8000 \
        --headless --users 20 --spawn-rate 5 --run-time 30s

The run fails (non-zero exit code) when the service level is not met:
- any request of a business endpoint failed,
- the 95th percentile response time of a business endpoint is above P95_LIMIT_MS.
Registration and setup requests are named "setup: ..." and excluded from the SLA,
because password hashing is deliberately slow.
"""

import logging
import os
import uuid

from locust import HttpUser, between, events, task

P95_LIMIT_MS = int(os.getenv("P95_LIMIT_MS", "500"))
PASSWORD = "Str0ng-Passw0rd!"


class BankCustomer(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self):
        email = f"load.{uuid.uuid4().hex[:12]}@example.com"
        self.client.post(
            "/api/auth/register",
            json={"email": email, "password": PASSWORD, "full_name": "Load Test"},
            name="setup: register",
        )
        token = self.client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}, name="setup: login"
        ).json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"

        self.accounts = []
        for _ in range(2):
            account = self.client.post("/api/accounts", json={"currency": "KZT"}, name="setup: open account").json()
            self.accounts.append(account["id"])
        self.client.post(
            f"/api/accounts/{self.accounts[0]}/deposit", json={"amount": "100000.00"}, name="setup: deposit"
        )

    @task(5)
    def check_balance(self):
        self.client.get(f"/api/accounts/{self.accounts[0]}/balance", name="GET /api/accounts/{id}/balance")

    @task(3)
    def read_history(self):
        self.client.get(
            f"/api/accounts/{self.accounts[0]}/transactions?limit=20",
            name="GET /api/accounts/{id}/transactions",
        )

    @task(2)
    def transfer(self):
        # Money goes back and forth between the customer's own accounts, so it never runs out.
        src, dst = self.accounts if uuid.uuid4().int % 2 else self.accounts[::-1]
        with self.client.post(
            "/api/transfers",
            json={"from_account_id": src, "to_account_id": dst, "amount": "1.00"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
            name="POST /api/transfers",
            catch_response=True,
        ) as response:
            # 422 INSUFFICIENT_FUNDS is a valid business answer when the source happens to be empty.
            if response.status_code == 422 and response.json().get("code") == "INSUFFICIENT_FUNDS":
                response.success()


@events.quitting.add_listener
def check_service_level(environment, **_kwargs):
    problems = []
    for entry in environment.stats.entries.values():
        if entry.name.startswith("setup:"):
            continue
        if entry.num_failures:
            problems.append(f"{entry.method} {entry.name}: {entry.num_failures} failed requests")
        p95 = entry.get_response_time_percentile(0.95)
        if p95 > P95_LIMIT_MS:
            problems.append(f"{entry.method} {entry.name}: p95 {p95:.0f} ms > {P95_LIMIT_MS} ms")
    if problems:
        logging.error("Service level not met:\n  " + "\n  ".join(problems))
        environment.process_exit_code = 1
    else:
        logging.info("Service level met: no failures, p95 <= %s ms on all business endpoints", P95_LIMIT_MS)
